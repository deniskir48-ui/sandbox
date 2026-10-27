"""Тонкие обёртки над ffmpeg/ffprobe."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    pass


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    log.debug("ffmpeg %s", " ".join(args))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg завершился с ошибкой:\n{result.stderr[-2000:]}")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe не смог прочитать {path}: {result.stderr}")
    return float(json.loads(result.stdout)["format"]["duration"])
