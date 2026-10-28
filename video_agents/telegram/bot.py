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
from typing import Callable

from ..models import VideoIdea, manual_idea
from .api import TelegramAPI, TelegramError, inline
from .messages import send_job, stats_text

log = logging.getLogger(__name__)

IDEAS = "💡 Идеи"
MAKE = "🎬 Сделать ролик"
QUEUE = "📋 Очередь"
STATS = "💰 Расходы"
MENU = {
    "keyboard": [[{"text": IDEAS}, {"text": MAKE}], [{"text": QUEUE}, {"text": STATS}]],
    "resize_keyboard": True,
    "is_persistent": True,
}
HELP = (
    "Я управляю роликами.\n\n"
    f"{IDEAS} - придумаю 5 тем, понравившиеся нажмите - они встанут в очередь\n"
    f"{MAKE} - сделаю ролик (тема из очереди или новая) и пришлю на проверку\n"
    f"{QUEUE} - темы, которые ждут своей очереди\n"
    f"{STATS} - сколько стоили ролики\n\n"
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
    def __init__(self, api: TelegramAPI, chat_id: int, pipeline, sync: bool = False):
        self.api = api
        self.chat_id = chat_id
        self.pipeline = pipeline
        self.worker = Worker(self._task_failed, sync=sync)
        self.idea_batches: dict[str, list[VideoIdea]] = {}
        self.offset = 0

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

    def _task_failed(self, title: str, exc: Exception) -> None:
        try:
            self.api.send(self.chat_id, f"❌ {title} - ошибка: {exc}")
        except Exception:
            log.exception("Не удалось сообщить об ошибке")

