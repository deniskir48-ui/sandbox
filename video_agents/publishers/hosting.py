"""Временная публичная ссылка на файл: Instagram (вход через Instagram) скачивает видео только по URL."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from .base import PublishError

log = logging.getLogger(__name__)

# litterbox.catbox.moe - бесплатный файлообменник без регистрации; файл удаляется сам через заданное время.
LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"


def upload_temporary(path: Path, lifetime: str = "1h") -> str:
    """Выкладывает файл на время (1h, 12h, 24h или 72h) и возвращает прямую ссылку."""
    log.info("Выкладываем видео по временной ссылке (удалится через %s)", lifetime)
    with open(path, "rb") as fh:
        response = requests.post(
            LITTERBOX_API,
            data={"reqtype": "fileupload", "time": lifetime},
            files={"fileToUpload": (path.name, fh, "video/mp4")},
            timeout=600,
        )
    url = response.text.strip()
    if not response.ok or not url.startswith("https://"):
        raise PublishError(f"Не удалось получить временную ссылку на видео: {response.status_code} {url[:300]}")
    return url
