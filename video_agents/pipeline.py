"""Оркестратор: ведёт ролик по конвейеру идея -> сценарий -> рендер -> публикация."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .agents import CriticAgent, IdeaAgent, MetadataAgent, ScriptwriterAgent
from .config import Settings
from .models import Job, UploadResult, VideoIdea
from .publishers import Publisher, make_publisher
from .storage import JobStore

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        llm=None,
        producer=None,
        publisher_factory: Callable[[str], Publisher] | None = None,
    ):
        self.settings = settings
        self.store = JobStore(settings.workspace)
        if llm is None:
            from .llm import LLM

            llm = LLM(settings.llm.model)
        channel = settings.channel
        self.idea_agent = IdeaAgent(llm, channel, web_research=settings.llm.web_research)
        self.writer = ScriptwriterAgent(llm, channel)
        self.critic = CriticAgent(llm, channel)
        self.meta_agent = MetadataAgent(llm, channel)
        self._producer = producer
        self.publisher_factory = publisher_factory or (lambda platform: make_publisher(platform, settings))

    @property
    def producer(self):
        # Создаём лениво: для генерации идей и публикации TTS/футажи не нужны.
        if self._producer is None:
            from .production import VideoProducer, make_footage, make_tts

            tts = make_tts(self.settings.voice, self.settings.secrets)
            footage = make_footage(self.settings.footage, self.settings.secrets, Path(self.settings.workspace) / "footage_cache")
            self._producer = VideoProducer(self.settings, tts, footage)
        return self._producer

    # --- Этапы ---

    def ideas(self, count: int) -> list[VideoIdea]:
        return self.idea_agent.generate(count, self.store.past_topics())

    def write(self, job: Job) -> Job:
        """Сценарист пишет, редактор критикует, до max_revisions кругов правок."""
        script = self.writer.write(job.idea)
        for round_ in range(self.settings.llm.max_revisions + 1):
            review = self.critic.review(job.idea, script)
            job.reviews.append(review)
            log.info("Редактор: %d/10 (%s)", review.score, "одобрено" if review.approved else "на доработку")
            if review.approved and review.score >= self.settings.llm.min_score:
                break
            if round_ == self.settings.llm.max_revisions:
                log.warning("Лимит правок исчерпан, берём последнюю версию сценария")
                break
            script = self.writer.revise(job.idea, script, review)
        job.script = script
        job.meta = self.meta_agent.generate(script)
        disclaimer = self.settings.channel.disclaimer.strip()
        if disclaimer:
            job.meta.youtube_description += f"\n\n{disclaimer}"
            job.meta.instagram_caption += f"\n\n{disclaimer}"
        job.status = "scripted"
        self.store.save(job)
        return job

    def produce(self, job: Job) -> Job:
        result = self.producer.produce(job.script, self.store.job_dir(job))
        job.video_path = str(result.video_path)
        job.duration = result.duration
        job.status = "produced"
        self.store.save(job)
        log.info("Ролик готов: %s (%.1f с)", result.video_path, result.duration)
        return job

    def publish(self, job: Job, platforms: list[str] | None = None) -> Job:
        if not job.video_path or not job.meta:
            raise RuntimeError(f"Ролик {job.id} ещё не смонтирован")
        for platform in platforms or self.settings.publish.platforms:
            if job.uploads.get(platform, UploadResult(platform=platform, ok=False)).ok:
                log.info("%s: уже опубликовано, пропускаем", platform)
                continue
            try:
                result = self.publisher_factory(platform).publish(Path(job.video_path), job.meta)
                log.info("%s: опубликовано %s", platform, result.url or result.id)
            except Exception as exc:
                log.error("%s: ошибка публикации: %s", platform, exc)
                result = UploadResult(platform=platform, ok=False, error=str(exc))
            job.uploads[platform] = result
            self.store.save(job)
        oks = [u.ok for u in job.uploads.values()]
        job.status = "published" if oks and all(oks) else "partially_published" if any(oks) else job.status
        self.store.save(job)
        return job

    # --- Полный цикл ---

    def run(self, count: int = 1, topic: str | None = None, publish: bool | None = None) -> list[Job]:
        publish = self.settings.publish.auto_publish if publish is None else publish
        if topic:
            ideas = [VideoIdea(topic=topic, angle="на усмотрение сценариста", hook="на усмотрение сценариста",
                               why_it_works="тема задана вручную")]
        else:
            ideas = self.ideas(count)
        jobs = []
        for idea in ideas:
            job = Job(idea=idea)
            self.store.save(job)
            log.info("=== Ролик %s: %s ===", job.id, idea.topic)
            try:
                self.write(job)
                self.produce(job)
                if publish:
                    self.publish(job)
            except Exception as exc:
                log.exception("Ролик %s упал", job.id)
                job.status = "failed"
                job.error = str(exc)
                self.store.save(job)
            jobs.append(job)
        return jobs
