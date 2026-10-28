from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from ..models import PlatformMeta, UploadResult


class PublishError(RuntimeError):
    pass


class Publisher(ABC):
    name: str

    @abstractmethod
    def publish(self, video_path: Path, meta: PlatformMeta) -> UploadResult: ...


def wait_until(check: Callable[[], bool], timeout: float = 600, interval: float = 5) -> None:
    """Опрашивает check(), пока он не вернёт True; check сам бросает исключение при ошибке."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(interval)
    raise PublishError(f"Платформа не обработала видео за {timeout:.0f} с")
