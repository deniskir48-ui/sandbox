from __future__ import annotations

import base64

from pydantic import BaseModel, Field

SYSTEM = """Ты - монтажёр коротких роликов. Тебе показывают превью стоковых видео и текст,
который в этот момент произносит диктор. Выбери кадр, который прямо иллюстрирует сказанное:
зритель должен сразу увидеть связь между словами и картинкой.

Отклоняй варианты, где:
- кадр про другое (текст про сон, а на видео еда);
- видны чужие логотипы, водяные знаки, крупный текст;
- картинка тёмная, размытая или неэстетичная;
- кадр противоречит смыслу (текст «не делай так», а на видео это показано как пример для подражания - допустимо,
  только если это и есть иллюстрация ошибки).

Если ни один вариант не подходит, честно ответь 0 - тогда поищем по другому запросу."""


class ClipChoice(BaseModel):
    best: int = Field(description="Номер лучшего варианта (1..N) или 0, если ни один не подходит")
    reason: str = Field(description="Коротко: почему этот вариант или почему ни один")


def _media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class FootageEditorAgent:
    def __init__(self, llm):
        self.llm = llm

    def choose(self, narration: str, title: str, previews: list[bytes]) -> int | None:
        """Индекс лучшего превью (с нуля) или None, если ни одно не подходит."""
        content: list[dict] = []
        for number, image in enumerate(previews, 1):
            content.append({"type": "text", "text": f"Вариант {number}:"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": _media_type(image),
                           "data": base64.b64encode(image).decode()},
            })
        content.append({
            "type": "text",
            "text": f"Ролик: {title}\nДиктор в этой сцене говорит: «{narration}»\n\n"
                    f"Какой из {len(previews)} вариантов лучше всего подходит к этим словам?",
        })
        choice = self.llm.structured(system=SYSTEM, prompt=content, output_model=ClipChoice,
                                     effort="low", max_tokens=8000)
        return choice.best - 1 if 1 <= choice.best <= len(previews) else None
