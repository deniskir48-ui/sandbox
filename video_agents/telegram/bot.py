"""Telegram-бот: управление системой с телефона.

Долгие задачи (идеи, ролик, публикация) выполняются по одной в фоновом потоке, а бот в это время
отвечает на сообщения. Слушается только владелец - чат, привязанный командой auth telegram.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import zlib
from pathlib import Path
from typing import Callable

from ..models import VideoIdea, manual_idea
from .api import TelegramAPI, TelegramError, inline
from .messages import send_job, stats_text

log = logging.getLogger(__name__)

IDEAS = "💡 Идеи"
MAKE = "🎬 Сделать ролик"
QUEUE = "📋 Очередь"
STATS = "💰 Расходы"
THREADS = "📊 Threads"
TRENDS = "🔥 Тренды"
MENU = {
    "keyboard": [[{"text": IDEAS}, {"text": MAKE}], [{"text": QUEUE}, {"text": STATS}],
                 [{"text": THREADS}, {"text": TRENDS}]],
    "resize_keyboard": True,
    "is_persistent": True,
}
HELP = (
    "Я управляю роликами.\n\n"
    f"{IDEAS} - придумаю 5 тем, понравившиеся нажмите - они встанут в очередь\n"
    f"{MAKE} - сделаю ролик (тема из очереди или новая) и пришлю на проверку\n"
    f"{QUEUE} - темы, которые ждут своей очереди\n"
    f"{STATS} - сколько стоили ролики\n"
    f"{THREADS} - статистика ваших постов в Threads и таблица для Excel\n"
    f"{TRENDS} - что сейчас в тренде в Threads\n"
    "/format - подобрать формат канала по вашим постам в Threads\n\n"
    "Любое другое сообщение я добавлю в очередь как тему ролика."
)
STALE_SECONDS = 300  # команды, отправленные, пока бот был выключен, не выполняем


def topic_tag(topic: str) -> str:
    """Короткая метка темы для кнопок: защищает от удаления не той темы, если очередь сдвинулась."""
    return format(zlib.crc32(topic.encode("utf-8")), "08x")


class Worker(threading.Thread):
    """Выполняет долгие задачи по одной; sync=True - сразу (для тестов)."""

    def __init__(self, on_error: Callable[[str, Exception], None], sync: bool = False):
        super().__init__(daemon=True)
        self.tasks: queue.Queue = queue.Queue()
        self.on_error = on_error
        self.sync = sync
        self.current: str | None = None

    def submit(self, title: str, fn: Callable[[], None]) -> int:
        """Ставит задачу; возвращает, сколько задач перед ней."""
        if self.sync:
            self._execute(title, fn)
            return 0
        ahead = self.tasks.qsize() + (1 if self.current else 0)
        self.tasks.put((title, fn))
        return ahead

    def run(self) -> None:
        while True:
            title, fn = self.tasks.get()
            self._execute(title, fn)

    def _execute(self, title: str, fn: Callable[[], None]) -> None:
        self.current = title
        try:
            fn()
        except Exception as exc:
            log.exception("Задача «%s» упала", title)
            self.on_error(title, exc)
        finally:
            self.current = None


class Bot:
    def __init__(self, api: TelegramAPI, chat_id: int, pipeline, sync: bool = False,
                 config_path: Path = Path("config.yaml")):
        self.api = api
        self.chat_id = chat_id
        self.pipeline = pipeline
        self.worker = Worker(self._task_failed, sync=sync)
        self.idea_batches: dict[str, list[VideoIdea]] = {}
        self.config_path = config_path
        self.proposal = None  # предложенный формат канала, ждёт подтверждения
        self.offset = 0
        self._message_id = None  # последнее сообщение владельца (чтобы удалить присланный ключ)

    # --- Цикл опроса Telegram ---

    def run_forever(self) -> None:
        self.worker.start()
        self.api.send(self.chat_id, "🤖 Бот запущен.", MENU)
        log.info("Бот запущен, жду сообщений")
        while True:
            try:
                # Длинный опрос: Telegram держит запрос до 50 секунд, пока не придёт сообщение.
                updates = self.api.call("getUpdates", http_timeout=70, timeout=50, offset=self.offset,
                                        allowed_updates=["message", "callback_query"])
            except TelegramError as exc:
                if exc.code == 409:
                    log.error("Этот бот уже запущен в другом окне - второй экземпляр завершается")
                    return
                log.warning("Telegram: %s", exc)
                time.sleep(5)
                continue
            except Exception as exc:  # обрыв сети - подождать и продолжить
                log.warning("Нет связи с Telegram: %s", exc)
                time.sleep(10)
                continue
            for update in updates:
                self.offset = update["update_id"] + 1
                try:
                    self.handle(update)
                except Exception:
                    log.exception("Не удалось обработать сообщение")

    def handle(self, update: dict) -> None:
        if "callback_query" in update:
            query = update["callback_query"]
            if query["message"]["chat"]["id"] != self.chat_id:
                return
            self.api.call("answerCallbackQuery", callback_query_id=query["id"])
            self.on_button(query["data"], query["message"])
            return
        message = update.get("message") or {}
        if message.get("chat", {}).get("id") != self.chat_id:
            return  # чужие чаты игнорируем: бот частный
        if time.time() - message.get("date", time.time()) > STALE_SECONDS:
            return
        self._message_id = message.get("message_id")
        self.on_text((message.get("text") or "").strip())

    # --- Текстовые команды ---

    def on_text(self, text: str) -> None:
        if not text:
            return
        if text in ("/start", "/help", "/menu") or text.startswith("/start "):
            self.api.send(self.chat_id, HELP, MENU)
        elif text in (IDEAS, "/ideas"):
            self._submit("Придумываю темы", self._make_ideas)
        elif text in (MAKE, "/make"):
            self._submit("Делаю ролик", self._make_video)
        elif text in (QUEUE, "/queue"):
            self._show_queue()
        elif text in (STATS, "/stats"):
            self.api.send(self.chat_id, stats_text(self.pipeline.store.all()))
        elif text.startswith("/threads "):
            self._connect_threads(text.split(maxsplit=1)[1])
        elif text == "/format" or text.startswith("/format "):
            hint = text[len("/format"):].strip()
            self._submit("Изучаю ваши посты в Threads", lambda: self._propose_format(hint))
        elif text.startswith("/threads_app "):
            self._connect_trends(text.split()[1:])
        elif text in (TRENDS, "/trends"):
            self._submit("Смотрю тренды Threads", self._show_trends)
        elif text in (THREADS, "/threads"):
            self._submit("Выгружаю статистику Threads", self._threads_report)
        elif text.startswith("/"):
            self.api.send(self.chat_id, HELP, MENU)
        else:
            self.pipeline.enqueue([manual_idea(text)])
            position = len(self.pipeline.store.queue())
            self.api.send(self.chat_id, f"➕ Тема добавлена в очередь (№{position}): {text}")

    # --- Кнопки под сообщениями ---

    def on_button(self, data: str, message: dict) -> None:
        kind, _, arg = data.partition(":")
        if kind == "i":  # тема из пачки идей -> в очередь
            batch, _, index = arg.partition(":")
            self._queue_ideas(batch, [int(index)], message)
        elif kind == "ia":
            self._queue_ideas(arg, list(range(len(self.idea_batches.get(arg, [])))), message)
        elif kind == "p":
            self._submit("Публикую ролик", lambda: self._publish(arg))
        elif kind == "r":
            self._submit("Пересобираю видео", lambda: self._rerender(arg))
        elif kind == "d":
            self._reject(arg, message)
        elif kind == "fa":  # применить предложенный формат с выбранным голосом
            self._apply_format(arg)
        elif kind == "fx":
            self.proposal = None
            self.api.send(self.chat_id, "Хорошо, формат не меняю.")
        elif kind == "tp":  # посты по тренду
            self._submit("Ищу посты по тренду", lambda: self._trend_posts(arg))
        elif kind == "qd":  # убрать тему из очереди
            index, _, tag = arg.partition(":")
            self._remove_from_queue(int(index), tag)

    # --- Действия ---

    def _submit(self, title: str, fn: Callable[[], None]) -> None:
        ahead = self.worker.submit(title, fn)
        if ahead:
            self.api.send(self.chat_id, f"⏳ {title} - встал в очередь, передо мной задач: {ahead}")

    def _progress_message(self, title: str):
        """Одно сообщение «⏳ ...», которое обновляется по ходу работы."""
        message = self.api.send(self.chat_id, f"⏳ {title}...")

        def update(text: str) -> None:
            try:
                self.api.edit(self.chat_id, message["message_id"], f"⏳ {text}...")
            except TelegramError as exc:
                log.debug("Не удалось обновить статус: %s", exc)

        return message, update

    def _with_progress(self, title: str, fn: Callable[[], None]) -> None:
        message, update = self._progress_message(title)
        self.pipeline.progress = update
        try:
            fn()
        finally:
            self.pipeline.progress = lambda text: None
            try:
                self.api.call("deleteMessage", chat_id=self.chat_id, message_id=message["message_id"])
            except TelegramError:
                pass

    def _make_ideas(self) -> None:
        ideas: list[VideoIdea] = []
        self._with_progress("Придумываю темы", lambda: ideas.extend(self.pipeline.ideas(5)))
        batch = format(int(time.time()), "x")
        self.idea_batches = {batch: ideas}  # кнопки работают только у последней пачки
        lines = ["Темы для роликов (нажмите, чтобы добавить в очередь):", ""]
        for number, idea in enumerate(ideas, 1):
            lines.append(f"{number}. {idea.topic} ({idea.relatability}/10)\n   {idea.viewer_problem}")
        self.api.send(self.chat_id, "\n".join(lines), self._ideas_keyboard(batch, set()))

    def _ideas_keyboard(self, batch: str, queued: set[int]) -> dict:
        ideas = self.idea_batches.get(batch, [])
        numbers = [(f"✅ {i + 1}" if i in queued else f"➕ {i + 1}", f"i:{batch}:{i}") for i in range(len(ideas))]
        return inline([numbers, [("➕ Все в очередь", f"ia:{batch}")]])

    def _queue_ideas(self, batch: str, indexes: list[int], message: dict) -> None:
        ideas = self.idea_batches.get(batch)
        if not ideas:
            self.api.send(self.chat_id, "Эти темы устарели - запросите новые: " + IDEAS)
            return
        queued = {topic for topic in (idea.topic for idea in self.pipeline.store.queue())}
        fresh = [ideas[i] for i in indexes if 0 <= i < len(ideas) and ideas[i].topic not in queued]
        if fresh:
            self.pipeline.enqueue(fresh)
        queued |= {idea.topic for idea in fresh}
        marked = {i for i, idea in enumerate(ideas) if idea.topic in queued}
        self.api.call("editMessageReplyMarkup", chat_id=self.chat_id, message_id=message["message_id"],
                      reply_markup=self._ideas_keyboard(batch, marked))
        if fresh:
            self.api.send(self.chat_id, f"➕ В очереди тем: {len(self.pipeline.store.queue())}")

    def _make_video(self) -> None:
        publish = self.pipeline.settings.publish.auto_publish
        jobs = []
        self._with_progress("Делаю ролик", lambda: jobs.extend(self.pipeline.run(count=1, publish=publish)))
        for job in jobs:
            send_job(self.api, self.chat_id, job)

    def _publish(self, job_id: str) -> None:
        job = self.pipeline.store.load(job_id)
        self._with_progress("Публикую", lambda: self.pipeline.publish(job))
        if not job.uploads:
            self.api.send(self.chat_id, "Ни одна площадка не подключена - публиковать некуда.")
            return
        send_job(self.api, self.chat_id, job, with_video=False)

    def _rerender(self, job_id: str) -> None:
        job = self.pipeline.store.load(job_id)
        self._with_progress("Пересобираю видео", lambda: self.pipeline.produce(job))
        send_job(self.api, self.chat_id, job)

    def _reject(self, job_id: str, message: dict) -> None:
        job = self.pipeline.store.load(job_id)
        if job.status in ("published", "partially_published"):
            self.api.send(self.chat_id, "Этот ролик уже опубликован - удалите его в самой соцсети.")
            return
        job.status = "rejected"
        self.pipeline.store.save(job)
        try:
            self.api.call("editMessageReplyMarkup", chat_id=self.chat_id, message_id=message["message_id"],
                          reply_markup=inline([]))
        except TelegramError:
            pass
        self.api.send(self.chat_id, "🗑 Ролик отклонён и не будет опубликован.")

    def _show_queue(self) -> None:
        ideas = self.pipeline.store.queue()
        if not ideas:
            self.api.send(self.chat_id, f"Очередь пуста. Нажмите {IDEAS} или просто напишите тему сообщением.")
            return
        lines = ["Очередь тем (следующий ролик - №1):", ""]
        lines += [f"{number}. {idea.topic}" for number, idea in enumerate(ideas, 1)]
        buttons = [(f"🗑 {i + 1}", f"qd:{i}:{topic_tag(idea.topic)}") for i, idea in enumerate(ideas[:8])]
        rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
        self.api.send(self.chat_id, "\n".join(lines), inline(rows))

    def _remove_from_queue(self, index: int, tag: str) -> None:
        with self.pipeline.store.lock:
            ideas = self.pipeline.store.queue()
            if not (0 <= index < len(ideas)) or topic_tag(ideas[index].topic) != tag:
                self.api.send(self.chat_id, "Очередь изменилась - откройте её заново: " + QUEUE)
                return
            removed = ideas.pop(index)
            self.pipeline.store.save_queue(ideas)
        self.api.send(self.chat_id, f"🗑 Убрал из очереди: {removed.topic}")

    def _connect_threads(self, token: str) -> None:
        from ..threads import ThreadsAuth, ThreadsError

        try:  # ключ не должен оставаться в переписке
            self.api.call("deleteMessage", chat_id=self.chat_id, message_id=self._message_id)
        except TelegramError:
            pass
        try:
            data = ThreadsAuth(self.pipeline.settings.secrets).save(token)
        except ThreadsError as exc:
            self.api.send(self.chat_id, f"❌ Ключ не подошёл: {exc}")
            return
        self.api.send(self.chat_id, f"✅ Threads @{data['username']} подключён. Нажмите {THREADS}, чтобы выгрузить посты.")

    def _propose_format(self, hint: str) -> None:
        from ..agents.channel_advisor import ChannelAdvisorAgent, proposal_text
        from ..reformat import VOICES
        from ..threads import load_posts, refresh

        workspace = Path(self.pipeline.settings.workspace)
        holder = {}

        def work() -> None:
            posts = load_posts(workspace) or refresh(self.pipeline.settings.secrets, workspace)
            holder["proposal"] = ChannelAdvisorAgent(self.pipeline.llms["ideas"]).propose(posts, hint, "ru")

        self._with_progress("Изучаю ваши посты в Threads и подбираю формат", work)
        self.proposal = holder["proposal"]
        keyboard = inline([[(f"✅ Применить, {VOICES['male'][0]} голос", "fa:male")],
                           [(f"✅ Применить, {VOICES['female'][0]} голос", "fa:female")],
                           [("❌ Не менять", "fx")]])
        self.api.send(self.chat_id, "Предлагаю такой формат канала:\n\n" + proposal_text(self.proposal), keyboard)

    def _apply_format(self, voice_key: str) -> None:
        from ..reformat import VOICES, apply_proposal

        if not self.proposal or voice_key not in VOICES:
            self.api.send(self.chat_id, "Предложение устарело - отправьте /format ещё раз.")
            return
        removed = apply_proposal(self.pipeline, self.config_path, self.proposal, "ru", VOICES[voice_key][1])
        topics = len(self.proposal.example_topics)
        self.proposal = None
        text = f"✅ Формат канала обновлён. В очереди {topics} новых тем - нажмите {MAKE}, чтобы снять первую."
        if removed:
            text += f"\nСтарые темы ({removed}) убраны из очереди и сохранены в резервную копию."
        self.api.send(self.chat_id, text)

    def _connect_trends(self, parts: list[str]) -> None:
        from ..threads import ThreadsApp, ThreadsError

        try:  # секрет приложения не должен оставаться в переписке
            self.api.call("deleteMessage", chat_id=self.chat_id, message_id=self._message_id)
        except TelegramError:
            pass
        if len(parts) != 2:
            self.api.send(self.chat_id, "Формат: /threads_app ID СЕКРЕТ (через пробел)")
            return
        try:
            trends = ThreadsApp(self.pipeline.settings.secrets).save(
                parts[0], parts[1], self.pipeline.settings.threads.trends_country)
        except ThreadsError as exc:
            self.api.send(self.chat_id, f"❌ Не подошло: {exc}")
            return
        self.api.send(self.chat_id, f"✅ Тренды подключены, сейчас их {len(trends)}. Нажмите {TRENDS}.")

    def _show_trends(self) -> None:
        from ..threads import ThreadsApp, fetch_trends

        country = self.pipeline.settings.threads.trends_country
        trends = fetch_trends(ThreadsApp(self.pipeline.settings.secrets).token(), country)
        if not trends:
            self.api.send(self.chat_id, "Сейчас Threads не отдаёт трендов.")
            return
        lines = [f"🔥 Тренды Threads ({country}) прямо сейчас:", ""]
        for n, trend in enumerate(trends, 1):
            lines.append(f"{n}. {trend['title']}" + (f"\n   {trend['description']}" if trend.get("description") else ""))
        lines += ["", "Кнопки ниже - популярные посты по тренду. Если тренд вдохновил, напишите мне свою тему "
                      "для ролика - она встанет в очередь."]
        buttons = [(f"📰 {n}", f"tp:{trend['trend_id']}") for n, trend in enumerate(trends[:12], 1)]
        self.api.send(self.chat_id, "\n".join(lines), inline([buttons[i:i + 6] for i in range(0, len(buttons), 6)]))

    def _trend_posts(self, trend_id: str) -> None:
        from ..threads import ThreadsApp, fetch_trend_posts

        posts = fetch_trend_posts(ThreadsApp(self.pipeline.settings.secrets).token(), trend_id)
        if not posts:
            self.api.send(self.chat_id, "По этому тренду постов не нашлось.")
            return
        lines = ["📰 Популярные посты по тренду:", ""]
        for post in posts:
            text = " ".join((post.get("text") or "").split())
            lines.append(f"@{post.get('username', '?')}: {text[:200]}\n{post.get('permalink', '')}\n")
        self.api.send(self.chat_id, "\n".join(lines))

    def _threads_report(self) -> None:
        from pathlib import Path

        from ..threads import describe, refresh, top_posts

        workspace = Path(self.pipeline.settings.workspace)
        posts: list[dict] = []
        self._with_progress("Выгружаю посты и статистику из Threads",
                            lambda: posts.extend(refresh(self.pipeline.settings.secrets, workspace)))
        best = top_posts(posts)
        lines = [f"📊 Threads: выгружено постов {len(posts)}. Лучшие по просмотрам:", ""]
        lines += [f"{n}. {describe(post)}" for n, post in enumerate(best, 1)]
        lines += ["", "Агент идей теперь учитывает эти посты."]
        self.api.send(self.chat_id, "\n".join(lines))
        self.api.send_document(self.chat_id, workspace / "threads_posts.xlsx", "Все посты со статистикой - таблица Excel")

    def _task_failed(self, title: str, exc: Exception) -> None:
        try:
            self.api.send(self.chat_id, f"❌ {title} - ошибка: {exc}")
        except Exception:
            log.exception("Не удалось сообщить об ошибке")

