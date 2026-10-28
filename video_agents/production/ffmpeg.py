"""Тонкие обёртки над ffmpeg/ffprobe."""

from __future__ import annotations

import json
import logging
import re
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


def probe_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    stream = json.loads(result.stdout or "{}").get("streams", [{}])[0]
    return int(stream.get("width", 0)), int(stream.get("height", 0))


def detect_black_borders(path: Path, sample: float = 3.0) -> str | None:
    """Находит чёрные полосы по краям видео; возвращает фильтр «crop=w:h:x:y» или None."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", "0.5", "-i", str(path), "-t", str(sample),
         "-vf", "cropdetect=limit=24:round=2:reset=0", "-an", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", result.stderr)
    if not matches:
        return None
    # reset=0: последняя строка - рамка, объединяющая все кадры, то есть самая осторожная.
    w, h, x, y = map(int, matches[-1])
    src_w, src_h = probe_size(path)
    if not src_w or not src_h or (w >= src_w * 0.97 and h >= src_h * 0.97):
        return None
    if w < src_w * 0.3 or h < src_h * 0.3:  # почти весь кадр тёмный - это сцена, а не рамка
        return None
    return f"crop={w}:{h}:{x}:{y}"
