"""Картинки, нарисованные ИИ, - последний вариант кадра, когда на стоках нет ни видео, ни фото.

По умолчанию - бесплатный Pollinations: без ключа картинки скромного качества и с водяным знаком внизу
(его срезаем при монтаже). С бесплатным ключом POLLINATIONS_TOKEN (auth.pollinations.ai) - лучше и без знака.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

STYLE = ("photorealistic photo, natural light, vertical composition, "
         "no text, no letters, no signs, no captions, no watermark")


class PollinationsImages:
    URL = "https://image.pollinations.ai/prompt/"
    name = "pollinations"

    def __init__(self, cache_dir: Path, token: str | None = None, width: int = 1080, height: int = 1920,
                 attempts: int = 3, pause: float = 5.0):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.width, self.height = width, height
        self.attempts, self.pause = attempts, pause

    @property
    def watermarked(self) -> bool:
        return not self.token

    def generate(self, subject: str, seed: int = 1) -> Path:
        prompt = f"{subject.strip()}, {STYLE}"
        key = hashlib.sha1(f"{prompt}|{seed}|{bool(self.token)}".encode()).hexdigest()[:16]
        path = self.cache_dir / f"ai_{key}.jpg"
        if path.exists() and path.stat().st_size > 0:
            return path
        params = {"width": self.width, "height": self.height, "nologo": "true", "seed": seed, "model": "flux"}
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = requests.get(self.URL + quote(prompt), params=params, headers=headers, timeout=180)
                response.raise_for_status()
                if not response.headers.get("Content-Type", "").startswith("image/"):
                    raise RuntimeError(f"вместо картинки пришло {response.headers.get('Content-Type')}")
                path.write_bytes(response.content)
                return path
            except Exception as exc:  # сервис бесплатный: бывает занят - пробуем ещё раз
                error = exc
                log.info("Генератор картинок не ответил (попытка %d): %s", attempt + 1, exc)
                time.sleep(self.pause * (attempt + 1))
        raise RuntimeError(f"генератор картинок недоступен: {error}")


def make_ai_images(footage_config, secrets, cache_dir: Path):
    if footage_config.ai_images == "pollinations":
        return PollinationsImages(cache_dir, secrets.pollinations_token)
    return None
