"""Запуск по расписанию через Планировщик задач Windows (schtasks).

Каждое время запуска - отдельная ежедневная задача «VideoAgents ЧЧ-ММ», которая выполняет run_scheduled.bat:
тот делает ролик (из очереди тем или новый) и публикует его, а вывод пишет в workspace/schedule.log.
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
from pathlib import Path

TASK_PREFIX = "VideoAgents"
ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "run_scheduled.bat"
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ScheduleError(RuntimeError):
    pass


def _schtasks(*args: str) -> str:
    if os.name != "nt":
        raise ScheduleError("Планировщик задач есть только в Windows. На Mac/Linux используйте cron (см. README).")
    # Русская Windows печатает в консольной кодировке (cp866), а не в UTF-8.
    result = subprocess.run(["schtasks", *args], capture_output=True, text=True, encoding="oem", errors="replace")
    if result.returncode != 0:
        raise ScheduleError((result.stderr or result.stdout).strip())
    return result.stdout


def normalize_time(value: str) -> str:
    match = TIME_RE.match(value.strip())
    if not match:
        raise ScheduleError(f"Не понимаю время «{value}». Пишите как 10:00 или 18:30.")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def add(times: list[str], count: int = 1) -> list[str]:
    """Создаёт (или заменяет) ежедневные задачи на указанное время."""
    created = []
    for value in times:
        at = normalize_time(value)
        name = f"{TASK_PREFIX} {at.replace(':', '-')}"
        _schtasks("/Create", "/F", "/SC", "DAILY", "/ST", at, "/TN", name,
                  "/TR", f'"{LAUNCHER}" -n {count}')
        created.append(name)
    return created


def list_tasks() -> list[tuple[str, str]]:
    """(имя задачи, следующий запуск) для всех задач программы."""
    output = _schtasks("/Query", "/FO", "CSV", "/NH")
    tasks = []
    for row in csv.reader(io.StringIO(output)):
        if len(row) >= 2 and row[0].lstrip("\\").startswith(TASK_PREFIX):
            tasks.append((row[0].lstrip("\\"), row[1]))
    return sorted(set(tasks))


def remove_all() -> list[str]:
    removed = []
    for name, _ in list_tasks():
        _schtasks("/Delete", "/F", "/TN", name)
        removed.append(name)
    return removed
