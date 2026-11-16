"""Однократная настройка: привязать бота к чату владельца и запускать его вместе с Windows."""

from __future__ import annotations

import os
import random
import time
from pathlib import Path

from .api import TelegramAccess, TelegramAPI

ROOT = Path(__file__).resolve().parents[2]
STARTUP_NAME = "VideoAgentsBot.bat"


def pair(api: TelegramAPI, code: str, wait_seconds: int = 600) -> int:
    """Ждёт сообщение «/start <код>» и возвращает id этого чата: так бот узнаёт своего владельца."""
    deadline = time.monotonic() + wait_seconds
    offset = 0
    while time.monotonic() < deadline:
        for update in api.call("getUpdates", http_timeout=40, timeout=30, offset=offset,
                               allowed_updates=["message"]):
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            if (message.get("text") or "").strip() == f"/start {code}":
                api.call("getUpdates", http_timeout=10, offset=offset)  # подтверждаем полученное
                return message["chat"]["id"]
    raise TimeoutError("Не дождался сообщения с кодом. Запустите команду ещё раз.")


def new_code() -> str:
    return f"{random.SystemRandom().randint(0, 9999):04d}"


def connect(token: str, secrets, code: str | None = None, ask=print) -> TelegramAccess:
    api = TelegramAPI(token.strip())
    bot = api.call("getMe")
    code = code or new_code()
    ask(f"\nОткройте Telegram, найдите бота @{bot['username']} и отправьте ему сообщение:\n\n"
        f"    /start {code}\n\nЖду (до 10 минут)...")
    chat_id = pair(api, code)
    access = TelegramAccess(api.token, chat_id)
    access.save(secrets)
    api.send(chat_id, "✅ Бот подключён! Теперь ролики можно делать и публиковать прямо отсюда.")
    return access


def startup_folder() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if os.name != "nt" or not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_autostart() -> Path | None:
    """Кладёт в автозагрузку Windows запуск start_bot.bat в свёрнутом окне. Возвращает путь или None."""
    folder = startup_folder()
    if not folder:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    launcher = folder / STARTUP_NAME
    # cmd читает .bat в кодировке консоли, поэтому путь (он может быть с кириллицей) пишем в ней же.
    launcher.write_text(f'@echo off\r\nstart "Video Agents bot" /min "{ROOT / "start_bot.bat"}"\r\n',
                        encoding="oem", errors="replace")
    return launcher


def start_now(launcher: Path) -> None:
    if os.name == "nt":
        os.startfile(launcher)  # noqa: S606 - запускаем свой же .bat
