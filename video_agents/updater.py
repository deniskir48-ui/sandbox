"""Обновление программы до свежей версии с GitHub без git: скачивает архив и заменяет код."""

from __future__ import annotations

import io
import logging
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import requests

log = logging.getLogger(__name__)

REPO_ZIP = "https://codeload.github.com/deniskir48-ui/sandbox/zip/refs/heads/main"
# Файлы и папки пользователя: их обновление не трогает.
KEEP = {".env", "config.yaml", "workspace", "secrets", ".venv", "assets"}


def update(root: Path, url: str = REPO_ZIP, skip_suffixes: tuple[str, ...] = ()) -> list[str]:
    """Перезаписывает файлы программы в root; возвращает список обновлённых путей.

    skip_suffixes - не трогать файлы с такими расширениями (например .bat, пока они могут выполняться).
    """
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    root = root.resolve()
    old_requirements = (root / "requirements.txt").read_bytes() if (root / "requirements.txt").exists() else b""
    updated = []
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for member in archive.infolist():
            # В архиве всё лежит внутри папки вида «sandbox-main/».
            parts = Path(member.filename).parts[1:]
            if not parts or member.is_dir() or parts[0] in KEEP or ".." in parts:
                continue
            if Path(parts[-1]).suffix.lower() in skip_suffixes:
                continue
            target = (root / Path(*parts)).resolve()
            if root not in target.parents:
                continue
            data = archive.read(member)
            if target.exists() and target.read_bytes() == data:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            updated.append(Path(*parts).as_posix())
    if (root / "requirements.txt").read_bytes() != old_requirements:
        log.info("Изменились зависимости, устанавливаем")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(root / "requirements.txt")], check=True)
    return updated


def auto_update(root: Path, state_file: Path, interval_hours: float = 1.0) -> list[str]:
    """Тихое обновление не чаще раза в interval_hours. Ошибки (нет сети и т. п.) не мешают работе.

    Не работает в git-репозитории (рабочая копия разработчика: обновление затёрло бы правки).
    .bat-файлы не трогаем: Windows читает работающий .bat по ходу выполнения, подмена его сломает.
    Изменения кода вступают в силу со следующего запуска.
    """
    if (root / ".git").exists():
        return []
    try:
        last = float(state_file.read_text(encoding="utf-8")) if state_file.exists() else 0.0
    except ValueError:
        last = 0.0
    if time.time() - last < interval_hours * 3600:
        return []
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(str(time.time()), encoding="utf-8")
    try:
        changed = update(root, skip_suffixes=(".bat",))
    except Exception as exc:
        log.warning("Автообновление не удалось (продолжаем на текущей версии): %s", exc)
        return []
    if changed:
        log.info("Программа обновилась автоматически: %d файл(ов)", len(changed))
    return changed
