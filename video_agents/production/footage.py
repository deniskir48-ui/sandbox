"""Подбор стоковых видео для фона (Pexels или Pixabay, оба бесплатные)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger(__name__)


@dataclass
class Clip:
    id: int
    duration: float
    url: str


class StockFootage:
    """Общая логика: поиск, выбор ролика нужной длины, скачивание в кэш."""

    name = "stock"

    def __init__(self, api_key: str, cache_dir: Path):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def find(self, query: str, min_duration: float, exclude: set[int]) -> tuple[int, Path] | None:
        """Возвращает (id видео, путь к файлу) или None, если ничего не нашлось."""
        for attempt in (query, " ".join(query.split()[:2])):
            candidates = [clip for clip in self._search(attempt) if clip.id not in exclude]
            if not candidates:
                continue
            # Предпочитаем ролики, которые не придётся зацикливать.
            candidates.sort(key=lambda clip: (clip.duration < min_duration, -clip.duration))
            clip = candidates[0]
            return clip.id, self._download(clip)
        return None

    def _search(self, query: str) -> list[Clip]:
        raise NotImplementedError

    def _download(self, clip: Clip) -> Path:
        path = self.cache_dir / f"{self.name}_{clip.id}.mp4"
        if path.exists() and path.stat().st_size > 0:
            return path
        with requests.get(clip.url, stream=True, timeout=120) as response:
            response.raise_for_status()
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as fh:
                for chunk in response.iter_content(1 << 20):
                    fh.write(chunk)
            tmp.replace(path)
        return path


class PexelsFootage(StockFootage):
    name = "pexels"
    SEARCH_URL = "https://api.pexels.com/videos/search"

    def _search(self, query: str) -> list[Clip]:
        response = requests.get(
            self.SEARCH_URL,
            headers={"Authorization": self.api_key},
            params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15},
            timeout=30,
        )
        response.raise_for_status()
        clips = []
        for video in response.json().get("videos", []):
            files = [
                f for f in video.get("video_files", [])
                if f.get("file_type") == "video/mp4" and f.get("height") and f.get("width")
                and f["height"] >= f["width"]
            ]
            if files:
                # Ближайший к 1920 по высоте, но не огромный 4K - экономим трафик и время рендера.
                best = min(files, key=lambda f: abs(f["height"] - 1920))
                clips.append(Clip(video["id"], video["duration"], best["link"]))
        return clips


class PixabayFootage(StockFootage):
    """Вертикальных роликов на Pixabay мало, поэтому берём любые и обрезаем под 9:16."""

    name = "pixabay"
    SEARCH_URL = "https://pixabay.com/api/videos/"
    MAX_SIZE = 80 * 1024 * 1024

    def _search(self, query: str) -> list[Clip]:
        response = requests.get(
            self.SEARCH_URL,
            params={"key": self.api_key, "q": query[:100], "video_type": "film",
                    "safesearch": "true", "min_height": 1080, "per_page": 20},
            timeout=30,
        )
        response.raise_for_status()
        clips = []
        for hit in response.json().get("hits", []):
            sizes = hit.get("videos", {})
            # large - обычно Full HD или 4K; слишком тяжёлые файлы заменяем на medium.
            for key in ("large", "medium"):
                video = sizes.get(key) or {}
                if video.get("url") and 0 < video.get("size", 0) <= self.MAX_SIZE:
                    clips.append(Clip(hit["id"], hit.get("duration", 0), video["url"]))
                    break
        return clips


def make_footage(footage_config, secrets, cache_dir: Path) -> StockFootage | None:
    provider = footage_config.provider
    if provider in ("auto", "pexels") and secrets.pexels_api_key:
        return PexelsFootage(secrets.pexels_api_key, cache_dir)
    if provider in ("auto", "pixabay") and secrets.pixabay_api_key:
        return PixabayFootage(secrets.pixabay_api_key, cache_dir)
    if provider != "none":
        log.warning("Нет ключа PEXELS_API_KEY или PIXABAY_API_KEY - вместо видео будут цветные фоны")
    return None
