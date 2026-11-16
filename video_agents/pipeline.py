"""Оркестратор: ведёт ролик по конвейеру идея -> сценарий -> рендер -> публикация."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .agents import CriticAgent, FootageEditorAgent, IdeaAgent, MetadataAgent, ScriptwriterAgent
from .agents.brief import word_budget
from .config import Settings
from .models import Job, UploadResult, VideoIdea, manual_idea
from .publishers import Publisher, is_configured, make_publisher
from .storage import JobStore

log = logging.getLogger(__name__)

ROLES = ("ideas", "script", "critic", "footage", "metadata", "screen")


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        llm=None,
        producer=None,
        publisher_factory: Callable[[str], Publisher] | None = None,
        platform_ready: Callable[[str], bool] | None = None,
        progress: Callable[[str], None] | None = None,
    ):
        self.settings = settings
        # Сообщения о ходе работы (например, для Telegram): «пишу сценарий», «монтирую видео».
        self.progress = progress or (lambda text: None)
        self.store = JobStore(settings.workspace)
        self.ledger = None
        if llm is None:
            import anthropic

            from .llm import LLM, CostLedger

            self.ledger = CostLedger()
            client = anthropic.Anthropic()
            self.llms = {role: LLM(settings.llm.model_for(role), client, self.ledger, role) for role in ROLES}
        else:
            self.llms = dict.fromkeys(ROLES, llm)
        channel = settings.channel
        self.idea_agent = IdeaAgent(self.llms["ideas"], channel, web_research=settings.llm.web_research)
        self.writer = ScriptwriterAgent(self.llms["script"], channel)
        self.critic = CriticAgent(self.llms["critic"], channel)
        self.meta_agent = MetadataAgent(self.llms["metadata"], channel)
        self._producer = producer
        self.publisher_factory = publisher_factory or (lambda platform: make_publisher(platform, settings))
        if platform_ready is None:
            platform_ready = (lambda platform: True) if publisher_factory else (
                lambda platform: is_configured(platform, settings))
        self.platform_ready = platform_ready

    @property
    def producer(self):
        # Создаём лениво: для генерации идей и публикации TTS/футажи не нужны.
        if self._producer is None:
            from .production import VideoProducer, make_footage, make_tts

            tts = make_tts(self.settings.voice, self.settings.secrets)
            footage = make_footage(self.settings.footage, self.settings.secrets, Path(self.settings.workspace) / "footage_cache")
            editor = FootageEditorAgent(self.llms["footage"]) if footage and self.settings.footage.ai_selection else None
            self._producer = VideoProducer(self.settings, tts, footage, editor)
        return self._producer

    # --- Этапы ---

    def ideas(self, count: int) -> list[VideoIdea]:
        from .threads import ideas_context

        signals = ideas_context(self.settings.secrets, Path(self.settings.workspace))
        if signals:
            log.info("Агент идей учитывает лучшие посты из Threads")
        ideas = self.idea_agent.generate(count, self.store.past_topics(), signals)
        self.store.log_ideas(ideas)
        return ideas

    def threads_ideas(self, count: int) -> list[VideoIdea]:
        """Следующие посты из Threads для переделки в ролики (от старых к новым, каждый один раз)."""
        from . import threads

        workspace = Path(self.settings.workspace)
        posts = threads.load_posts(workspace, max_age_hours=24)  # свежим постам нужна свежая статистика
        if posts is None:
            try:
                posts = threads.refresh(self.settings.secrets, workspace)
            except Exception as exc:
                log.warning("Не удалось обновить посты из Threads: %s", exc)
                posts = threads.load_posts(workspace) or []
        used = {job.idea.source_post_id for job in self.store.all()
                if job.idea and job.idea.source_post_id and job.status != "failed"}
        config = self.settings.threads
        fresh = threads.recent_posts(posts, used, config.fresh_days, config.min_post_chars)
        backlog = threads.pick_posts(posts, used, len(posts), config.min_views, config.min_age_days,
                                     config.min_post_chars)
        picked = self._screen_posts(fresh, backlog, count)
        if picked:
            log.info("Берём %d пост(а) из Threads для переделки в ролики", len(picked))
        else:
            log.info("Подходящих постов в Threads нет - тему придумает агент идей")
        return [threads.post_to_idea(post) for post in picked]

    def _screen_posts(self, fresh: list[dict], backlog: list[dict], count: int) -> list[dict]:
        """Сначала свежие посты с датами (афиши) - вне очереди, затем остальные от старых к новым.

        Отборщик пропускает вопросы без ответа (и посты не по теме, если включён threads.topic_filter);
        посты с датами вне окна свежести считаются устаревшими. Решения запоминаются.
        """
        from . import threads
        from .agents.post_screener import PostScreenerAgent

        workspace = Path(self.settings.workspace)
        topic_filter = self.settings.threads.topic_filter
        key = f"{self.settings.channel.niche}|topic_filter={topic_filter}"  # сменились правила - проверяем заново
        verdicts = threads.load_screening(workspace, key)
        screener = PostScreenerAgent(self.llms["screen"], self.settings.channel, topic_filter)

        def judge(batch: list[dict]) -> bool:
            unknown = [post for post in batch if str(post["id"]) not in verdicts]
            if not unknown:
                return True
            try:
                verdicts.update(screener.screen(unknown))
            except Exception as exc:
                log.warning("Не удалось проверить посты: %s", exc)
                return False
            threads.save_screening(workspace, verdicts, key)
            return True

        def short(post: dict) -> str:
            return " ".join(post.get("text", "").split())[:60]

        picked: list[dict] = []
        for start in range(0, len(fresh), 10):  # 1. свежие афиши и события - пока не устарели
            batch = fresh[start:start + 10]
            if not judge(batch):
                return picked
            for post in batch:
                verdict = verdicts.get(str(post["id"]), {})
                if verdict.get("use") and verdict.get("time_sensitive"):
                    log.info("Свежий пост с датами - берём вне очереди: %s", short(post))
                    picked.append(post)
                    if len(picked) == count:
                        return picked
        fresh_ids = {post["id"] for post in fresh}
        rest = [post for post in backlog if post not in picked]
        for start in range(0, len(rest), 10):  # 2. остальные - от старых к новым
            batch = rest[start:start + 10]
            if not judge(batch):
                return picked
            for post in batch:
                verdict = verdicts.get(str(post["id"]))
                if not verdict:
                    continue
                if not verdict["use"]:
                    log.info("Пропускаем пост: %s - %s", short(post), verdict["reason"])
                elif verdict.get("time_sensitive"):
                    if post["id"] not in fresh_ids:
                        log.info("Пропускаем устаревший пост с датами: %s", short(post))
                else:
                    picked.append(post)
                    if len(picked) == count:
                        return picked
        return picked

    def enqueue(self, ideas: list[VideoIdea]) -> None:
        with self.store.lock:
            self.store.save_queue(self.store.queue() + ideas)

    def _next_ideas(self, count: int) -> list[VideoIdea]:
        """Сначала темы из очереди, затем посты из Threads (если включено), остальное придумывает агент идей."""
        with self.store.lock:
            queue = self.store.queue()
            taken, rest = queue[:count], queue[count:]
            self.store.save_queue(rest)
        if taken:
            log.info("Берём %d тем(ы) из очереди, осталось %d", len(taken), len(rest))
        if len(taken) < count and self.settings.channel.source == "threads":
            taken += self.threads_ideas(count - len(taken))
        if len(taken) < count:
            self.progress("Придумываю темы")
            taken += self.ideas(count - len(taken))
        return taken

    def write(self, job: Job) -> Job:
        """Сценарист пишет, редактор критикует, до max_revisions кругов правок."""
        with self._costs(job):
            self.progress(f"Пишу сценарий: {job.idea.topic}")
            script = self.writer.write(job.idea)
            for round_ in range(self.settings.llm.max_revisions + 1):
                review = self.critic.review(job.idea, script)
                job.reviews.append(review)
                log.info("Редактор: %d/10 (%s)", review.score, "одобрено" if review.approved else "на доработку")
                self.progress(f"Редактор: {review.score}/10, " + ("одобрено" if review.approved else "на доработку"))
                if review.approved and review.score >= self.settings.llm.min_score:
                    break
                if round_ == self.settings.llm.max_revisions:
                    log.warning("Лимит правок исчерпан, берём последнюю версию сценария")
                    break
                script = self.writer.revise(job.idea, script, review)
            script = self._fit_length(job, script)
            job.script = script
            job.meta = self.meta_agent.generate(script)
            disclaimer = self.settings.channel.disclaimer.strip()
            if disclaimer:
                job.meta.youtube_description += f"\n\n{disclaimer}"
                job.meta.instagram_caption += f"\n\n{disclaimer}"
            job.status = "scripted"
            return job

    @contextmanager
    def _costs(self, job: Job):
        """Записывает в ролик, сколько стоили обращения к Claude внутри блока (даже при сбое)."""
        mark = self.ledger.mark() if self.ledger else 0
        try:
            yield
        finally:
            if self.ledger:
                self._add_cost(job, self.ledger.since(mark))
            self.store.save(job)

    @staticmethod
    def _add_cost(job: Job, costs: dict[str, float]) -> None:
        for stage, cost in costs.items():
            job.cost_by_stage[stage] = round(job.cost_by_stage.get(stage, 0.0) + cost, 4)
        job.cost_usd = round(sum(job.cost_by_stage.values()), 4)

    def _fit_length(self, job: Job, script):
        """Жёсткая проверка длины: модель не всегда считает слова, поэтому считаем сами."""
        budget = word_budget(self.settings.channel)
        for _ in range(2):
            words = len(script.full_text.split())
            if words <= budget * 1.1:
                break
            log.info("Сценарий длиннее лимита (%d слов при лимите %d), сокращаем", words, budget)
            script = self.writer.shorten(job.idea, script)
        return script

    def produce(self, job: Job) -> Job:
        with self._costs(job):
            self.progress("Монтирую видео: озвучка, подбор кадров, субтитры")
            result = self.producer.produce(job.script, self.store.job_dir(job))
            job.video_path = str(result.video_path)
            job.duration = result.duration
            job.status = "produced"
        log.info("Ролик готов: %s (%.1f с)", result.video_path, result.duration)
        return job

    def publish(self, job: Job, platforms: list[str] | None = None) -> Job:
        if not job.video_path or not job.meta:
            raise RuntimeError(f"Ролик {job.id} ещё не смонтирован")
        explicit = bool(platforms)
        for platform in platforms or self.settings.publish.platforms:
            if job.uploads.get(platform, UploadResult(platform=platform, ok=False)).ok:
                log.info("%s: уже опубликовано, пропускаем", platform)
                continue
            if not explicit and not self.platform_ready(platform):
                # Неподключённые площадки молча пропускаем: можно подключать их по одной.
                log.info("%s: не подключён, пропускаем (python -m video_agents auth %s)", platform, platform)
                continue
            try:
                self.progress(f"Публикую в {platform}")
                result = self.publisher_factory(platform).publish(Path(job.video_path), job.meta)
                log.info("%s: опубликовано %s", platform, result.url or result.id)
            except Exception as exc:
                log.error("%s: ошибка публикации: %s", platform, exc)
                result = UploadResult(platform=platform, ok=False, error=str(exc))
            job.uploads[platform] = result
            self.store.save(job)
        if not job.uploads:
            log.warning("Ни одна площадка не подключена - ролик не опубликован")
        oks = [u.ok for u in job.uploads.values()]
        job.status = "published" if oks and all(oks) else "partially_published" if any(oks) else job.status
        self.store.save(job)
        return job

    # --- Полный цикл ---

    def run(self, count: int = 1, topic: str | None = None, publish: bool | None = None,
            ideas: list[VideoIdea] | None = None) -> list[Job]:
        publish = self.settings.publish.auto_publish if publish is None else publish
        ideas_cost: dict[str, float] = {}
        if not ideas and topic:
            ideas = [manual_idea(topic)]
        elif not ideas:
            mark = self.ledger.mark() if self.ledger else 0
            ideas = self._next_ideas(count)
            ideas_cost = self.ledger.since(mark) if self.ledger else {}
        jobs = []
        for index, idea in enumerate(ideas):
            job = Job(idea=idea)
            if index == 0 and ideas_cost:
                self._add_cost(job, ideas_cost)  # поиск идей на всю пачку - в счёт первого ролика
            self.store.save(job)
            log.info("=== Ролик %s: %s ===", job.id, idea.topic)
            try:
                self.write(job)
                self.produce(job)
                if publish:
                    self.publish(job)
            except Exception as exc:
                log.exception("Ролик %s упал", job.id)
                if not topic:
                    # Хорошая тема не должна пропасть из-за сбоя: возвращаем её в конец очереди.
                    self.enqueue([idea])
                job.status = "failed"
                job.error = str(exc)
                self.store.save(job)
            jobs.append(job)
        return jobs
