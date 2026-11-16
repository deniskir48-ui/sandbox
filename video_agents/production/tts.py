"""Озвучка текста с пословными таймкодами (нужны для субтитров)."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from .ffmpeg import probe_duration

log = logging.getLogger(__name__)


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Speech:
    audio_path: Path
    duration: float
    words: list[Word]


class TTSProvider(Protocol):
    def synthesize(self, text: str, out_path: Path) -> Speech: ...


# Запасной голос того же языка: голоса Microsoft иногда по очереди «пропадают» на время.
FALLBACK_VOICES = {
    "ru-RU-DmitryNeural": "ru-RU-SvetlanaNeural",
    "ru-RU-SvetlanaNeural": "ru-RU-DmitryNeural",
    "en-US-AndrewMultilingualNeural": "en-US-AvaMultilingualNeural",
    "en-US-AvaMultilingualNeural": "en-US-AndrewMultilingualNeural",
    "en-US-ChristopherNeural": "en-US-AndrewMultilingualNeural",
}


class EdgeTTS:
    """Бесплатные нейроголоса Microsoft Edge (ru-RU-DmitryNeural, ru-RU-SvetlanaNeural, ...)."""

    def __init__(self, voice: str, rate: str = "+0%", attempts: int = 6, pause: float = 2.0):
        self.voice = voice
        self.rate = rate
        self.attempts = attempts
        self.pause = pause

    def use_fallback(self) -> bool:
        """Переключиться на запасной голос (для всего ролика). False - запасного нет."""
        fallback = FALLBACK_VOICES.get(self.voice)
        if not fallback:
            return False
        log.warning("Голос %s сейчас не отвечает - ролик озвучит %s", self.voice, fallback)
        self.voice = fallback
        return True

    def synthesize(self, text: str, out_path: Path) -> Speech:
        # Бесплатный сервис иногда отвечает пустотой - повторяем с паузой.
        for attempt in range(1, self.attempts + 1):
            try:
                words = asyncio.run(self._stream(text, out_path))
                return Speech(out_path, probe_duration(out_path), words)
            except Exception as exc:
                if attempt == self.attempts:
                    raise RuntimeError(
                        f"edge-tts не озвучил текст голосом {self.voice}: {exc}. "
                        "Попробуйте другой голос (voice.voice в config.yaml) или ElevenLabs."
                    ) from exc
                log.info("edge-tts: попытка %d не удалась (%s), повторяем", attempt, exc)
                time.sleep(self.pause * attempt)  # сбои идут волнами: ждём всё дольше, до полуминуты

    async def _stream(self, text: str, out_path: Path) -> list[Word]:
        import edge_tts

        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, boundary="WordBoundary")
        words: list[Word] = []
        with open(out_path, "wb") as audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7  # единицы по 100 нс
                    words.append(Word(chunk["text"], start, start + chunk["duration"] / 1e7))
        return words


class ElevenLabsTTS:
    """Платные, но очень естественные голоса ElevenLabs."""

    API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"

    def __init__(self, api_key: str, voice_id: str, model_id: str = "eleven_multilingual_v2"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id

    def synthesize(self, text: str, out_path: Path) -> Speech:
        response = requests.post(
            self.API.format(voice=self.voice_id),
            headers={"xi-api-key": self.api_key},
            json={"text": text, "model_id": self.model_id},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        out_path.write_bytes(base64.b64decode(data["audio_base64"]))
        alignment = data["alignment"]
        words = words_from_characters(
            alignment["characters"],
            alignment["character_start_times_seconds"],
            alignment["character_end_times_seconds"],
        )
        return Speech(out_path, probe_duration(out_path), words)


def words_from_characters(chars: list[str], starts: list[float], ends: list[float]) -> list[Word]:
    words: list[Word] = []
    current, start, end = "", 0.0, 0.0
    for char, char_start, char_end in zip(chars, starts, ends):
        if char.isspace():
            if current:
                words.append(Word(current, start, end))
            current = ""
            continue
        if not current:
            start = char_start
        current += char
        end = char_end
    if current:
        words.append(Word(current, start, end))
    return words


def make_tts(voice_config, secrets) -> TTSProvider:
    if voice_config.provider == "elevenlabs":
        if not secrets.elevenlabs_api_key:
            raise RuntimeError("Для ElevenLabs нужен ELEVENLABS_API_KEY в .env")
        return ElevenLabsTTS(secrets.elevenlabs_api_key, voice_config.voice, voice_config.elevenlabs_model)
    return EdgeTTS(voice_config.voice, voice_config.rate)
