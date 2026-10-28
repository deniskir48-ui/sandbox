"""Временная публичная ссылка на файл: Instagram (вход через Instagram) скачивает видео только по URL.

Бесплатные файлообменники без регистрации иногда отказывают (перегрузка, блокировка региона или программ),
поэтому пробуем несколько по очереди. Все они удаляют файл сами через несколько часов.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

import requests

from .base import PublishError

log = logging.getLogger(__name__)

# Некоторые сервисы не пускают запросы без «браузерного» User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36"}
TIMEOUT = 600


def _uguu(path: Path) -> str:
    """uguu.se: файл хранится около 3 часов, ответ - прямая ссылка текстом."""
    with open(path, "rb") as fh:
        response = requests.post("https://uguu.se/upload?output=text", headers=HEADERS,
                                 files={"files[]": (path.name, fh, "video/mp4")}, timeout=TIMEOUT)
    return _check(response, response.text.strip())


def _litterbox(path: Path) -> str:
    """litterbox.catbox.moe: файл удаляется через 1 час."""
    with open(path, "rb") as fh:
        response = requests.post("https://litterbox.catbox.moe/resources/internals/api.php", headers=HEADERS,
                                 data={"reqtype": "fileupload", "time": "1h"},
                                 files={"fileToUpload": (path.name, fh, "video/mp4")}, timeout=TIMEOUT)
    return _check(response, response.text.strip())


def _tmpfiles(path: Path) -> str:
    """tmpfiles.org: файл удаляется через 1 час; прямая ссылка - с префиксом /dl/."""
    with open(path, "rb") as fh:
        response = requests.post("https://tmpfiles.org/api/v1/upload", headers=HEADERS,
                                 files={"file": (path.name, fh, "video/mp4")}, timeout=TIMEOUT)
    try:
        page = response.json()["data"]["url"]
    except (ValueError, KeyError, TypeError):
        page = response.text
    url = re.sub(r"^https?://tmpfiles\.org/", "https://tmpfiles.org/dl/", page.strip())
    return _check(response, url)


def _check(response, url: str) -> str:
    if not response.ok or not url.startswith("https://"):
        raise PublishError(f"HTTP {response.status_code}: {_short(response.text)}")
    return url


def _short(text: str) -> str:
    """Ответ сервера без HTML-разметки, в одну короткую строку."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(text.split())[:120] or "пустой ответ"


HOSTS: list[tuple[str, Callable[[Path], str]]] = [
    ("uguu.se", _uguu),
    ("litterbox.catbox.moe", _litterbox),
    ("tmpfiles.org", _tmpfiles),
]


def upload_temporary(path: Path) -> str:
    """Выкладывает файл на первый сработавший файлообменник и возвращает прямую ссылку."""
    errors = []
    for name, upload in HOSTS:
        try:
            url = upload(path)
        except (requests.RequestException, PublishError) as exc:
            log.warning("%s не принял видео: %s", name, exc)
            errors.append(f"{name}: {exc}")
            continue
        log.info("Видео доступно по временной ссылке (%s)", name)
        return url
    raise PublishError("Не удалось получить временную ссылку на видео ни на одном сервисе. " + "; ".join(errors))
