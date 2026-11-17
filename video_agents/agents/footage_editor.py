from __future__ import annotations

import base64

from pydantic import BaseModel, Field

SYSTEM = """Ты - монтажёр коротких роликов. Тебе показывают превью стоковых видео или фото и текст,
который в этот момент произносит диктор. Выбери кадр, который прямо иллюстрирует сказанное:
зритель должен сразу увидеть связь между словами и картинкой.

Отклоняй варианты, где:
- кадр про другое (текст про сон, а на видео еда);
- видны чужие логотипы, водяные знаки, крупный текст;
- обнажёнка, полуголые люди, гламурные позы моделей, странная или пугающая картинка (кривые руки, лица,
  неестественные тела у нарисованных ИИ картинок);
- картинка тёмная, размытая или неэстетичная;
- кадр противоречит смыслу (текст «не делай так», а на видео это показано как пример для подражания - допустимо,
  только если это и есть иллюстрация ошибки).

Если ни один вариант не подходит, честно ответь 0 - тогда поищем по другому запросу.
Лучше ответить 0, чем выбрать кадр про другое: случайная картинка ломает ролик."""

RELAXED = """Точного кадра к этой сцене не нашлось. Выбери нейтральный кадр, который подходит хотя бы
к общей теме ролика и не сбивает зрителя с толку. Если все варианты про другое (например, косметика
в ролике про питание), ответь 0."""


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

    def choose(self, narration: str, title: str, previews: list[bytes], relaxed: bool = False) -> int | None:
        """Индекс лучшего превью (с нуля) или None, если ни одно не подходит.

        relaxed - второй проход: годится любой кадр по теме ролика, лишь бы не про другое.
        """
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
                    f"Какой из {len(previews)} вариантов лучше всего подходит к этим словам?"
                    + (f"\n\n{RELAXED}" if relaxed else ""),
        })
        choice = self.llm.structured(system=SYSTEM, prompt=content, output_model=ClipChoice,
                                     effort="low", max_tokens=8000)
        return choice.best - 1 if 1 <= choice.best <= len(previews) else None


# --- Свои кадры автора: описать файл один раз, потом подбирать к фразам по описаниям ---

DESCRIBE = """Ты помогаешь вести библиотеку личных видео и фото автора канала. Тебе показывают кадры из одного
файла. Опиши по-русски в 1-2 предложениях, что видно: место, предметы, люди и что они делают, время суток,
погода, настроение. Пиши конкретно и без оценок - по этому описанию потом будут подбирать кадр к словам
диктора (например: «Вход в аптеку с зелёным крестом на узкой улице, вечер, людей нет»)."""

MATCH = """Ты - монтажёр. Автор снял свои видео и фото; у каждого файла есть описание. Для каждой фразы диктора
выбери файл, который её иллюстрирует, - или хотя бы показывает подходящее место и настроение и не противоречит
словам. Свои кадры автора лучше стоковых, но случайный кадр про другое ломает ролик: если ничего не подходит,
ставь 0. По возможности не повторяй один файл в разных фразах, кроме соседних (тогда видео просто продолжается)."""


class FileDescription(BaseModel):
    description: str = Field(description="Что видно в файле, 1-2 предложения по-русски")


class LibraryPicks(BaseModel):
    picks: list[int] = Field(description="Для каждой фразы по порядку - номер файла (1..N) или 0, если ничего не подходит")


def describe_file(llm, frames: list[bytes], kind: str) -> str:
    content: list[dict] = []
    for number, image in enumerate(frames, 1):
        content.append({"type": "text", "text": f"Кадр {number}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": _media_type(image),
                                                    "data": base64.b64encode(image).decode()}})
    content.append({"type": "text", "text": "Это " + ("кадры из одного видео." if kind == "video" else "фотография.")})
    return llm.structured(system=DESCRIBE, prompt=content, output_model=FileDescription,
                          effort="low", max_tokens=2000).description.strip()


def match_library(llm, title: str, phrases: list[str], descriptions: list[str]) -> list[int | None]:
    """Для каждой фразы - индекс файла (с нуля) или None."""
    files = "\n".join(f"{n}. {text}" for n, text in enumerate(descriptions, 1))
    lines = "\n".join(f"{n}. «{text}»" for n, text in enumerate(phrases, 1))
    prompt = (f"Ролик: {title}\n\nФайлы автора:\n{files}\n\nФразы диктора:\n{lines}\n\n"
              f"Верни ровно {len(phrases)} номеров файлов - по одному на каждую фразу.")
    picks = llm.structured(system=MATCH, prompt=prompt, output_model=LibraryPicks, effort="low").picks
    picks = (list(picks) + [0] * len(phrases))[:len(phrases)]
    return [p - 1 if 1 <= p <= len(descriptions) else None for p in picks]
