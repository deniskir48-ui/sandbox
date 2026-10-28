"""Данные, которыми обмениваются агенты, и состояние одного ролика (Job)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


# --- Ответы агентов (structured outputs) ---


class VideoIdea(BaseModel):
    viewer_problem: str = Field(
        description="Знакомая зрителю проблема или вопрос - так, как сказал бы он сам (например 'I can't lose belly fat')"
    )
    relatability: int = Field(
        description="Сколько людей из аудитории узнают в этом себя, от 1 до 10 (10 - почти каждый)"
    )
    topic: str = Field(description="Тема ролика одной фразой")
    angle: str = Field(description="Чем ответ полезен и неожидан: простое конкретное решение знакомой проблемы")
    hook: str = Field(description="Первая фраза ролика: называет проблему зрителя и останавливает скролл")
    why_it_works: str = Field(description="Почему это зайдёт аудитории, 1-2 предложения")

    @model_validator(mode="before")
    @classmethod
    def _legacy_fields(cls, data):
        # Идеи, сохранённые до появления этих полей.
        if isinstance(data, dict):
            data = {"viewer_problem": data.get("topic", ""), "relatability": 0, **data}
        return data


class IdeaList(BaseModel):
    ideas: list[VideoIdea] = Field(description="Идеи, отсортированные от самой сильной к слабой")


class Scene(BaseModel):
    narration: str = Field(description="Текст диктора для сцены, 1-2 коротких предложения")
    visual_queries: list[str] = Field(
        description="2-3 запроса для поиска стокового видео НА АНГЛИЙСКОМ, по 2-4 слова, "
        "от самого точного к более общему; описывают то, что буквально видно в кадре"
    )
    on_screen_text: str = Field(description="Короткая надпись на экране (до 5 слов) или пустая строка")

    @model_validator(mode="before")
    @classmethod
    def _legacy_query(cls, data):
        # Ролики, сохранённые до появления нескольких запросов, хранили один visual_query.
        if isinstance(data, dict) and "visual_query" in data and "visual_queries" not in data:
            data = {**data, "visual_queries": [data.pop("visual_query")]}
        return data


class Script(BaseModel):
    title: str = Field(description="Рабочее название ролика")
    scenes: list[Scene] = Field(description="Сцены по порядку; первая сцена - хук")
    call_to_action: str = Field(description="Короткий призыв до 4 слов (уже включён в последнюю сцену) или пустая строка")
    backup_queries: list[str] = Field(
        description="2-3 общих запроса НА АНГЛИЙСКОМ по теме всего ролика (например 'coffee cup kitchen morning') - "
        "запасной видеоряд, если для сцены не найдётся точного кадра"
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_backup(cls, data):
        if isinstance(data, dict) and "backup_queries" not in data:
            data = {**data, "backup_queries": []}
        return data

    @property
    def full_text(self) -> str:
        return " ".join(scene.narration for scene in self.scenes)


class Review(BaseModel):
    score: int = Field(description="Оценка сценария от 1 до 10")
    approved: bool = Field(description="true, если сценарий можно отдавать в производство без правок")
    strengths: list[str] = Field(description="Что получилось хорошо")
    problems: list[str] = Field(description="Конкретные проблемы: хук, темп, фактические ошибки, вода, риски модерации")
    rewrite_instructions: str = Field(description="Чёткие указания автору, что исправить; пусто, если approved")


class PlatformMeta(BaseModel):
    youtube_title: str = Field(description="Заголовок YouTube Shorts, до 90 символов, без кликбейта-лжи")
    youtube_description: str = Field(description="Описание YouTube, 2-4 предложения + хэштеги, включая #shorts")
    youtube_tags: list[str] = Field(description="10-15 тегов YouTube без символа #")
    instagram_caption: str = Field(description="Подпись к Reels: цепляющая первая строка, текст, призыв, 5-10 хэштегов")
    tiktok_caption: str = Field(description="Подпись TikTok до 300 символов с 3-6 хэштегами")


# --- Состояние ролика ---


JobStatus = Literal["new", "scripted", "produced", "published", "partially_published", "failed"]


class UploadResult(BaseModel):
    platform: str
    ok: bool
    id: str | None = None
    url: str | None = None
    error: str | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Job(BaseModel):
    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: JobStatus = "new"
    idea: VideoIdea | None = None
    script: Script | None = None
    reviews: list[Review] = Field(default_factory=list)
    meta: PlatformMeta | None = None
    video_path: str | None = None
    duration: float | None = None
    uploads: dict[str, UploadResult] = Field(default_factory=dict)
    error: str | None = None
