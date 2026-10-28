"""Минимальный клиент Telegram Bot API (без сторонних библиотек) и сохранённый доступ к боту."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import requests

API_URL = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    def __init__(self, description: str, code: int | None = None):
        super().__init__(description)
        self.code = code


def inline(rows: list[list[tuple[str, str]]]) -> dict:
    """Кнопки под сообщением: [[(текст, данные), ...], ...]."""
    return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}


class TelegramAPI:
    def __init__(self, token: str):
        self.token = token

    def call(self, method: str, files: dict | None = None, http_timeout: float = 60, **params):
        # Списки, словари и true/false Telegram ждёт в виде JSON.
        data = {key: json.dumps(value) if isinstance(value, (dict, list, bool)) else value
                for key, value in params.items() if value is not None}
        response = requests.post(API_URL.format(token=self.token, method=method), data=data, files=files,
                                 timeout=http_timeout)
        try:
            payload = response.json()
        except ValueError:
            raise TelegramError(f"HTTP {response.status_code}", response.status_code) from None
        if not payload.get("ok"):
            raise TelegramError(payload.get("description", "ошибка Telegram"), payload.get("error_code"))
        return payload["result"]

    def send(self, chat_id: int, text: str, keyboard: dict | None = None) -> dict:
        return self.call("sendMessage", chat_id=chat_id, text=text[:4096], reply_markup=keyboard,
                         disable_web_page_preview=True)

    def edit(self, chat_id: int, message_id: int, text: str, keyboard: dict | None = None) -> None:
        try:
            self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text[:4096],
                      reply_markup=keyboard, disable_web_page_preview=True)
        except TelegramError as exc:
            if "not modified" not in str(exc):
                raise

    def send_video(self, chat_id: int, path: Path, caption: str, keyboard: dict | None = None) -> dict:
        with open(path, "rb") as fh:
            return self.call("sendVideo", files={"video": (path.name, fh, "video/mp4")}, http_timeout=300,
                             chat_id=chat_id, caption=caption[:1024], supports_streaming="true",
                             reply_markup=keyboard)


@dataclass
class TelegramAccess:
    token: str
    chat_id: int

    @classmethod
    def load(cls, secrets) -> "TelegramAccess | None":
        path = Path(secrets.telegram_file)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["token"], int(data["chat_id"]))

    def save(self, secrets) -> None:
        path = Path(secrets.telegram_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"token": self.token, "chat_id": self.chat_id}), encoding="utf-8")
