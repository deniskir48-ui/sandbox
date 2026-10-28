"""Обновление программы до свежей версии с GitHub без git: скачивает архив и заменяет код."""

from __future__ import annotations

import io
import logging
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

log = logging.getLogger(__name__)

REPO_ZIP = "https://codeload.github.com/deniskir48-ui/sandbox/zip/refs/heads/main"
# Файлы и папки пользователя: их обновление не трогает.
KEEP = {".env", "config.yaml", "workspace", "secrets", ".venv", "assets"}


def update(root: Path, url: str = REPO_ZIP) -> list[str]:
    """Перезаписывает файлы программы в root; возвращает список обновлённых путей."""
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
