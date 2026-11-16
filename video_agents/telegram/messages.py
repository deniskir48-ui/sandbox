"""Как ролики и расходы выглядят в Telegram: общие для бота и уведомлений из расписания."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import Job
from .api import TelegramAPI, TelegramError, inline

log = logging.getLogger(__name__)

PLATFORM_NAMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}


def job_keyboard(job: Job) -> dict | None:
    if job.status in ("produced", "partially_published"):
        return inline([[("✅ Опубликовать", f"p:{job.id}"), ("🔄 Пересобрать", f"r:{job.id}"),
                        ("🗑 Удалить", f"d:{job.id}")]])
    return None


def job_caption(job: Job) -> str:
    lines = [f"🎬 {job.idea.topic if job.idea else job.id}"]
    details = []
    if job.duration:
        details.append(f"{job.duration:.0f} с")
    if job.cost_usd:
        details.append(f"${job.cost_usd:.2f}")
    if details:
        lines.append(" · ".join(details))
    for upload in job.uploads.values():
        name = PLATFORM_NAMES.get(upload.platform, upload.platform)
        lines.append(f"✅ {name}: {upload.url or upload.id}" if upload.ok else f"❌ {name}: {upload.error}")
    if job.status == "produced" and job.meta:
        lines += ["", job.meta.instagram_caption]
    return "\n".join(lines)


def send_job(api: TelegramAPI, chat_id: int, job: Job, with_video: bool = True) -> None:
    """Готовый ролик - видео с подписью и кнопками; неудачный - сообщение с причиной."""
    if job.status == "failed":
        topic = job.idea.topic if job.idea else job.id
        api.send(chat_id, f"❌ Ролик не получился: {topic}\nПричина: {job.error}")
        return
    caption = job_caption(job)
    video = Path(job.video_path) if job.video_path else None
    if with_video and video and video.exists():
        try:
            api.send_video(chat_id, video, caption, job_keyboard(job))
            return
        except TelegramError as exc:  # например, файл больше 50 МБ - пришлём текстом
            log.warning("Не удалось отправить видео в Telegram: %s", exc)
    api.send(chat_id, caption, job_keyboard(job))


def stats_text(jobs: list[Job]) -> str:
    paid = [job for job in jobs if job.cost_usd]
    published = [job for job in jobs if job.status in ("published", "partially_published")]
    lines = [f"Роликов: {len(jobs)}, опубликовано: {len(published)}"]
    if paid:
        total = sum(job.cost_usd for job in paid)
        lines.append(f"Расходы на Claude: ${total:.2f}, в среднем ${total / len(paid):.2f} за ролик")
    lines.append("")
    for job in jobs[-5:]:
        topic = job.idea.topic if job.idea else job.id
        lines.append(f"• {topic} - {job.status}" + (f", ${job.cost_usd:.2f}" if job.cost_usd else ""))
    return "\n".join(lines)


def notify_jobs(settings, jobs: list[Job]) -> None:
    """Сообщить владельцу о роликах (например, сделанных по расписанию), если бот подключён."""
    from .api import TelegramAccess

    access = TelegramAccess.load(settings.secrets)
    if not access:
        return
    api = TelegramAPI(access.token)
    for job in jobs:
        try:
            send_job(api, access.chat_id, job)
        except Exception as exc:  # уведомление не должно ломать сам запуск
            log.warning("Не удалось отправить уведомление в Telegram: %s", exc)
