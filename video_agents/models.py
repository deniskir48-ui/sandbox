"""Данные, которыми обмениваются агенты, и состояние одного ролика (Job)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


# --- Ответы агентов (structured outputs) ---


class VideoIdea(BaseModel):
    topic: str = Field(description="Тема ролика одной фразой")
    angle: str = Field(description="Неочевидный угол подачи: чем ролик отличается от тысячи похожих")
    hook: str = Field(description="Первая фраза ролика, которая останавливает скролл")
    why_it_works: str = Field(description="Почему это зайдёт аудитории, 1-2 предложения")


class IdeaList(BaseModel):
    ideas: list[VideoIdea] = Field(description="Идеи, отсортированные от самой сильной к слабой")


class Scene(BaseModel):
    narration: str = Field(description="Текст диктора для сцены, 1-2 коротких предложения")
    visual_query: str = Field(
        description="Запрос для стокового видео НА АНГЛИЙСКОМ, 2-4 слова, что конкретно видно в кадре"
    )
    on_screen_text: str = Field(description="Короткая надпись на экране (до 5 слов) или пустая строка")


class Script(BaseModel):
    title: str = Field(description="Рабочее название ролика")
    scenes: list[Scene] = Field(description="Сцены по порядку; первая сцена - хук")
    call_to_action: str = Field(description="Финальная фраза-призыв (подписка/комментарий), уже включена в последнюю сцену")

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
