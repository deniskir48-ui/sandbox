"""Подбор вертикальных стоковых видео (Pexels, бесплатно с атрибуцией по желанию)."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class PexelsFootage:
    SEARCH_URL = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str, cache_dir: Path):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def find(self, query: str, min_duration: float, exclude: set[int]) -> tuple[int, Path] | None:
        """Возвращает (id видео, путь к файлу) или None, если ничего не нашлось."""
        for attempt in (query, " ".join(query.split()[:2])):
            videos = self._search(attempt)
            candidates = [video for video in videos if video["id"] not in exclude]
            if not candidates:
                continue
            # Предпочитаем ролики, которые не придётся зацикливать.
            candidates.sort(key=lambda video: (video["duration"] < min_duration, -video["duration"]))
            video = candidates[0]
            file_url = self._best_file(video)
            if file_url:
                return video["id"], self._download(video["id"], file_url)
        return None

    def _search(self, query: str) -> list[dict]:
        response = requests.get(
            self.SEARCH_URL,
            headers={"Authorization": self.api_key},
            params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("videos", [])

    @staticmethod
    def _best_file(video: dict) -> str | None:
        files = [
            f for f in video.get("video_files", [])
            if f.get("file_type") == "video/mp4" and f.get("height") and f.get("width")
            and f["height"] >= f["width"]
        ]
        if not files:
            return None
        # Ближайший к 1920 по высоте, но не огромный 4K - экономим трафик и время рендера.
        files.sort(key=lambda f: abs(f["height"] - 1920))
        return files[0]["link"]

    def _download(self, video_id: int, url: str) -> Path:
        path = self.cache_dir / f"pexels_{video_id}.mp4"
        if path.exists() and path.stat().st_size > 0:
            return path
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as fh:
                for chunk in response.iter_content(1 << 20):
                    fh.write(chunk)
            tmp.rename(path)
        return path


def make_footage(footage_config, secrets, cache_dir: Path) -> PexelsFootage | None:
    if footage_config.provider == "pexels" and secrets.pexels_api_key:
        return PexelsFootage(secrets.pexels_api_key, cache_dir)
    log.warning("PEXELS_API_KEY не задан - вместо видео будут цветные фоны")
    return None
