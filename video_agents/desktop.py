"""Окно программы для Windows: страница в браузере с кнопками вместо команд в PowerShell.

Запуск: двойной щелчок по ярлыку «Видео-агент» на рабочем столе (его создаёт команда app при первом запуске).
Сервер слушает только 127.0.0.1, а каждое действие требует ключ, который знает лишь открытая страница:
чужие сайты не смогут нажать кнопки за вас.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

import requests

from .agents.brief import words_per_second
from .config import load_settings
from .models import Job, manual_idea
from .winproc import NO_WINDOW

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PAGE = Path(__file__).with_name("desktop_page.html")
PORT = 8765
SHORTCUT_NAME = "Видео-агент"
VOICES = {"male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"}
JOB_ID = re.compile(r"^[\w-]{1,64}$")
UPDATE_CHECK_SECONDS = 3600
IS_WINDOWS = os.name == "nt"


def topic_tag(topic: str) -> str:
    import zlib

    return format(zlib.crc32(topic.encode("utf-8")), "08x")


class Tasks:
    """Долгие задачи выполняются по одной в фоне; их ход виден на странице."""

    def __init__(self, sync: bool = False):
        self.sync = sync
        self.queue: queue.Queue = queue.Queue()
        self.current: str | None = None
        self.lines: collections.deque[dict] = collections.deque(maxlen=60)
        self.counter = 0
        self._lock = threading.Lock()
        if not sync:
            threading.Thread(target=self._loop, daemon=True).start()

    def say(self, text: str, kind: str = "info") -> None:
        with self._lock:
            self.counter += 1
            self.lines.append({"n": self.counter, "time": time.strftime("%H:%M:%S"), "text": text, "kind": kind})

    def submit(self, title: str, fn: Callable[[], None]) -> None:
        if self.sync:
            self._run(title, fn)
            return
        if self.current or not self.queue.empty():
            self.say(f"«{title}» - в очереди, начну после текущей задачи")
        self.queue.put((title, fn))

    @property
    def waiting(self) -> int:
        return self.queue.qsize()

    def idle(self) -> bool:
        return not self.current and self.queue.empty()

    def _loop(self) -> None:
        while True:
            title, fn = self.queue.get()
            self._run(title, fn)

    def _run(self, title: str, fn: Callable[[], None]) -> None:
        self.current = title
        self.say(f"▶ {title}")
        try:
            fn()
        except Exception as exc:
            log.exception("Задача «%s» упала", title)
            self.say(f"Ошибка: {exc}", "error")
        finally:
            self.current = None


class _TaskLog(logging.Handler):
    """Важные сообщения программы (предупреждения и ошибки) - в ленту на странице."""

    def __init__(self, tasks: Tasks):
        super().__init__(logging.WARNING)
        self.tasks = tasks

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("video_agents") and record.name != __name__:
            self.tasks.say(record.getMessage(), "error" if record.levelno >= logging.ERROR else "warn")


class DesktopApp:
    def __init__(self, config_path: Path, pipeline_factory: Callable[..., object] | None = None,
                 sync: bool = False):
        self.config_path = Path(config_path)
        self.tasks = Tasks(sync=sync)
        self.token = secrets.token_urlsafe(24)
        self._pipeline_factory = pipeline_factory
        self.next_posts: list[dict] | None = None
        self.restart_requested = False

    # --- Данные для страницы ---

    def settings(self):
        return load_settings(self.config_path)

    def pipeline(self):
        if self._pipeline_factory:
            return self._pipeline_factory()
        from .pipeline import Pipeline

        return Pipeline(self.settings(), progress=self.tasks.say)

    def state(self) -> dict:
        settings = self.settings()
        from .storage import JobStore

        store = JobStore(settings.workspace)
        jobs = store.all()
        paid = [job for job in jobs if job.cost_usd]
        total = sum(job.cost_usd for job in paid)
        with self.tasks._lock:
            lines = list(self.tasks.lines)
        return {
            "busy": self.tasks.current,
            "waiting": self.tasks.waiting,
            "log": lines,
            "jobs": [job_view(job) for job in reversed(jobs) if job.status != "rejected"][:30],
            "queue": [{"topic": idea.topic, "tag": topic_tag(idea.topic),
                       "from_threads": bool(idea.source_post_id)} for idea in store.queue()],
            "next_posts": self.next_posts,
            "settings": settings_view(settings),
            "connected": connections(settings),
            "library": library_view(settings),
            "daily": {**settings.daily.model_dump(include={"enabled", "time", "publish"}), **self.daily_state()},
            "notes": notes_view(settings),
            "stats": {"videos": len(jobs), "paid": len(paid), "total": round(total, 2),
                      "average": round(total / len(paid), 2) if paid else 0},
        }

    # --- Действия кнопок ---

    def action(self, name: str, data: dict) -> str:
        handler = getattr(self, f"do_{name}", None)
        if not handler:
            raise ValueError(f"Неизвестное действие: {name}")
        return handler(data) or ""

    def _job(self, data: dict) -> str:
        job_id = str(data.get("job", ""))
        if not JOB_ID.match(job_id):
            raise ValueError("Неверный номер ролика")
        return job_id

    def do_make(self, data: dict) -> str:
        topic = (data.get("topic") or "").strip() or None

        def work() -> None:
            job = self.pipeline().draft(topic)
            if job.status == "failed":
                self._report(job)
            else:
                self.tasks.say(f"Сценарий готов: «{job.idea.topic}». Он в блоке «Сценарии на проверке»: "
                               "поправьте при желании и нажмите «Снять видео».", "ok")

        self.tasks.submit("Пишу сценарий" + (f": {topic}" if topic else ""), work)
        return "Пишу сценарий: около минуты"

    def _report(self, job: Job) -> None:
        topic = job.idea.topic if job.idea else job.id
        if job.status == "failed":
            self.tasks.say(f"Ролик не получился: {topic}. Причина: {job.error}", "error")
            return
        if job.duration:
            self.tasks.say(f"Готово: «{topic}», {job.duration:.0f} с, ${job.cost_usd:.2f}", "ok")
        for upload in job.uploads.values():
            if upload.ok:
                self.tasks.say(f"{upload.platform}: опубликовано {upload.url or upload.id or ''}", "ok")
            else:
                self.tasks.say(f"{upload.platform}: ошибка {upload.error}", "error")

    def do_publish(self, data: dict) -> str:
        job_id = self._job(data)

        def work() -> None:
            pipeline = self.pipeline()
            job = pipeline.publish(pipeline.store.load(job_id))
            if not job.uploads:
                self.tasks.say("Ни одна соцсеть не подключена - публиковать некуда.", "error")
            self._report(job)

        self.tasks.submit("Публикую ролик", work)
        return "Публикую"

    def do_rerender(self, data: dict) -> str:
        job_id = self._job(data)

        def work() -> None:
            pipeline = self.pipeline()
            self._report(pipeline.produce(pipeline.store.load(job_id)))

        self.tasks.submit("Пересобираю видео", work)
        return "Пересобираю видео по тому же сценарию (это бесплатно)"

    def _lines(self, data: dict) -> list[str] | None:
        text = data.get("text")
        return None if text is None else [line for line in str(text).splitlines() if line.strip()]

    @staticmethod
    def _draft(store, job_id: str) -> Job:
        job = store.load(job_id)
        if not job.script:
            raise ValueError("У ролика ещё нет сценария")
        if any(upload.ok for upload in job.uploads.values()):
            raise ValueError("Этот ролик уже опубликован - сделайте новый")
        return job

    def do_approve(self, data: dict) -> str:
        """«Снять видео»: сохраняем правки текста (если были) и монтируем; публикуем, если включено."""
        job_id, lines = self._job(data), self._lines(data)

        def work() -> None:
            pipeline = self.pipeline()
            job = self._draft(pipeline.store, job_id)
            if lines is not None and lines != [scene.narration for scene in job.script.scenes]:
                pipeline.edit_script(job, lines)
            try:
                pipeline.produce(job)
                if pipeline.settings.publish.auto_publish:
                    pipeline.publish(job)
            except Exception as exc:
                job.status, job.error = "scripted", str(exc)  # сценарий не теряем: можно снять ещё раз
                pipeline.store.save(job)
                raise
            self._report(job)

        self.tasks.submit("Монтирую видео", work)
        return "Монтирую видео: пара минут"

    def do_save_script(self, data: dict) -> str:
        job_id, lines = self._job(data), self._lines(data) or []

        def work() -> None:
            pipeline = self.pipeline()
            pipeline.edit_script(self._draft(pipeline.store, job_id), lines)
            self.tasks.say("Правки сохранены", "ok")

        self.tasks.submit("Сохраняю правки", work)
        return "Сохраняю"

    def do_redraft(self, data: dict) -> str:
        job_id, comment = self._job(data), str(data.get("comment") or "")

        def work() -> None:
            pipeline = self.pipeline()
            job = pipeline.redraft(self._draft(pipeline.store, job_id), comment)
            self.tasks.say(f"Новый вариант сценария готов, ${job.cost_usd:.2f} за ролик всего", "ok")

        self.tasks.submit("Пишу другой вариант сценария", work)
        return "Пишу другой вариант"

    def do_edit(self, data: dict) -> str:
        """Вернуть готовый, но не опубликованный ролик к правке текста (бесплатно)."""
        from .storage import JobStore

        store = JobStore(self.settings().workspace)
        job = self._draft(store, self._job(data))
        job.status = "scripted"
        store.save(job)
        return "Текст открыт для правки"

    def do_reject(self, data: dict) -> str:
        from .storage import JobStore

        store = JobStore(self.settings().workspace)
        job = store.load(self._job(data))
        if job.status in ("published", "partially_published"):
            return "Этот ролик уже опубликован - удалите его в самой соцсети"
        job.status = "rejected"
        store.save(job)
        return "Ролик убран из списка"

    def do_open_folder(self, data: dict) -> str:
        from .storage import JobStore

        folder = JobStore(self.settings().workspace).job_dir(self._job(data))
        open_path(folder)
        return ""

    def do_queue_add(self, data: dict) -> str:
        text = (data.get("text") or "").strip()
        if not text:
            return "Напишите тему"
        from .storage import JobStore

        store = JobStore(self.settings().workspace)
        with store.lock:
            store.save_queue(store.queue() + [manual_idea(text)])
        return "Тема добавлена в очередь"

    def do_queue_remove(self, data: dict) -> str:
        from .storage import JobStore

        store = JobStore(self.settings().workspace)
        with store.lock:
            ideas = store.queue()
            index = int(data.get("index", -1))
            if not 0 <= index < len(ideas) or topic_tag(ideas[index].topic) != data.get("tag"):
                return "Очередь уже изменилась - обновите страницу"
            del ideas[index]
            store.save_queue(ideas)
        return "Тема убрана"

    def do_next_posts(self, data: dict) -> str:
        def work() -> None:
            ideas = self.pipeline().threads_ideas(5)
            self.next_posts = [{"text": " ".join(idea.source_text.split())[:300], "why": idea.why_it_works}
                               for idea in ideas]
            self.tasks.say(f"Следующих постов для роликов: {len(ideas)}", "ok")

        self.tasks.submit("Смотрю, какие посты пойдут в ролики", work)
        return "Подбираю посты"

    def do_exclude(self, data: dict) -> str:
        text = (data.get("text") or "").strip()
        if not text:
            return "Напишите тему"
        from .config_edit import add_to_list

        add_to_list(self.config_path, "threads.exclude_topics", text)
        self.next_posts = None
        return f"Посты на тему «{text}» больше не пойдут в ролики"

    def do_open_library(self, data: dict) -> str:
        from .production.library import open_folder

        folder = open_folder(Path(self.settings().footage.library_dir))
        return f"Папка открыта: {folder.resolve()}"

    def do_study_library(self, data: dict) -> str:
        def work() -> None:
            from .production.library import make_library

            settings = self.settings()
            pipeline = self.pipeline()
            library = make_library(settings.footage, Path(settings.workspace) / "footage_cache",
                                   pipeline.llms["footage"])
            if not library:
                self.tasks.say("В папке пока нет видео и фото", "error")
                return
            items = library.scan(self.tasks.say)
            self.tasks.say(f"Изучено ваших кадров: {len(items)}. Они пойдут в ролики в первую очередь.", "ok")

        self.tasks.submit("Изучаю ваши кадры", work)
        return "Изучаю ваши кадры"

    def do_threads_report(self, data: dict) -> str:
        def work() -> None:
            from . import threads

            settings = self.settings()
            posts = threads.refresh(settings.secrets, Path(settings.workspace))
            table = Path(settings.workspace) / "threads_posts.xlsx"
            self.tasks.say(f"Выгружено постов: {len(posts)}. Открываю таблицу.", "ok")
            open_path(table)

        self.tasks.submit("Выгружаю посты из Threads", work)
        return "Выгружаю"

    def do_setting(self, data: dict) -> str:
        from .config_edit import set_value

        key, value = data.get("key"), data.get("value")
        if key == "speed":
            set_value(self.config_path, "voice.rate", f"'{int(value):+d}%'")
        elif key == "voice":
            set_value(self.config_path, "voice.voice", VOICES[value])
        elif key == "length":
            length = int(value)
            set_value(self.config_path, "channel.video_length_seconds", str(length))
            maximum = self.settings().channel.max_video_length_seconds
            if maximum < length:
                set_value(self.config_path, "channel.max_video_length_seconds", str(length))
        elif key == "daily_enabled":
            set_value(self.config_path, "daily.enabled", "true" if value else "false")
            if value and IS_WINDOWS:
                link = install_autostart(str(self.config_path))
                return ("Включено. Программа будет запускаться вместе с Windows и делать ролик сама"
                        if link else "Включено (автозапуск с Windows настроить не удалось)")
        elif key == "daily_time":
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(value)):
                raise ValueError("Время в формате ЧЧ:ММ")
            set_value(self.config_path, "daily.time", f"'{value}'")
        elif key == "daily_publish":
            set_value(self.config_path, "daily.publish", "true" if value else "false")
        elif key == "library_dir":
            folder = Path(str(value).strip().strip('"'))
            if not str(folder).strip() or not folder.is_dir():
                raise ValueError("Такой папки нет - проверьте путь")
            set_value(self.config_path, "footage.library_dir", json.dumps(str(folder.resolve())))
        elif key == "library_only":
            set_value(self.config_path, "footage.library_only", "true" if value else "false")
        elif key in ("auto_publish", "show_scene_text"):
            section = "publish" if key == "auto_publish" else "subtitles"
            set_value(self.config_path, f"{section}.{key}", "true" if value else "false")
        else:
            raise ValueError(f"Неизвестная настройка: {key}")
        return "Сохранено"

    def do_update(self, data: dict) -> str:
        def work() -> None:
            from .updater import update

            changed = update(ROOT, skip_suffixes=(".bat",))
            if changed:
                self.tasks.say(f"Программа обновлена ({len(changed)} файл(ов)), перезапускаюсь...", "ok")
                self.restart_requested = True
            else:
                self.tasks.say("У вас уже последняя версия", "ok")

        self.tasks.submit("Проверяю обновления", work)
        return "Проверяю обновления"

    # --- Ролик дня ---

    @property
    def daily_state_file(self) -> Path:
        return Path(self.settings().workspace) / "daily_state.json"

    def daily_state(self) -> dict:
        try:
            return json.loads(self.daily_state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_daily_state(self, **values) -> None:
        state = {**self.daily_state(), **values}
        self.daily_state_file.parent.mkdir(parents=True, exist_ok=True)
        self.daily_state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def daily_due(self, now: datetime | None = None) -> bool:
        """Пора ли делать ролик дня: включено, время настало, сегодня ещё не делали, программа свободна.
        Если компьютер был выключен в назначенное время, ролик сделается, как только окно запустится."""
        now = now or datetime.now()
        daily = self.settings().daily
        return (daily.enabled and now.strftime("%H:%M") >= daily.time
                and self.daily_state().get("last_date") != now.date().isoformat() and self.tasks.idle())

    def run_daily(self, publish: bool | None = None) -> None:
        self._save_daily_state(last_date=date.today().isoformat())  # даже при сбое - не больше раза в день

        def work() -> None:
            pipeline = self.pipeline()
            job = pipeline.daily(publish)
            self._save_daily_state(last_job=job.id, last_topic=job.idea.topic if job.idea else "",
                                   last_status=job.status)
            self._report(job)
            if job.status == "produced":
                self.tasks.say("Ролик дня готов и ждёт вашей проверки - кнопка «Опубликовать» под ним.", "ok")
            try:
                from .telegram.messages import notify_jobs

                notify_jobs(pipeline.settings, [job])
            except Exception as exc:
                log.warning("Уведомление в Telegram не отправлено: %s", exc)

        self.tasks.submit("Ролик дня", work)

    def daily_loop(self) -> None:
        while True:
            try:
                if self.daily_due():
                    self.run_daily()
            except Exception as exc:
                log.warning("Расписание ролика дня: %s", exc)
            time.sleep(30)

    def do_daily_now(self, data: dict) -> str:
        self.run_daily(publish=bool(data.get("publish", self.settings().daily.publish)))
        return "Делаю ролик дня: тема, сценарий, монтаж - минут 5-10"

    def do_note_add(self, data: dict) -> str:
        from .notes import Notes

        text = (data.get("text") or "").strip()
        if not text:
            return "Напишите набросок"
        Notes(Path(self.settings().workspace)).add(text)
        return "Набросок сохранён"

    def do_note_remove(self, data: dict) -> str:
        from .notes import Notes

        Notes(Path(self.settings().workspace)).remove(str(data.get("id", "")))
        return "Набросок удалён"

    def auto_update_loop(self, server: ThreadingHTTPServer) -> None:
        """Раз в час, когда ничего не делается, тихо обновляет программу и перезапускает окно."""
        from . import updater

        while True:
            if self.restart_requested and self.tasks.idle():
                server.shutdown()
                return
            try:
                settings = self.settings()
                if self.tasks.idle() and settings.auto_update:
                    if updater.auto_update(ROOT, Path(settings.workspace) / ".last_update_check"):
                        self.tasks.say("Вышла новая версия программы, перезапускаюсь...", "ok")
                        self.restart_requested = True
                        continue
            except Exception as exc:  # например, config.yaml правится прямо сейчас - проверим в следующий раз
                log.warning("Проверка обновлений не удалась: %s", exc)
            time.sleep(5 if self.restart_requested else 60)


def job_view(job: Job) -> dict:
    return {
        "id": job.id,
        "topic": job.idea.topic if job.idea else job.id,
        "status": job.status,
        "duration": round(job.duration or 0),
        "cost": round(job.cost_usd, 2),
        "has_video": bool(job.video_path and Path(job.video_path).exists()),
        "from_threads": bool(job.idea and job.idea.source_post_id),
        "caption": job.meta.instagram_caption if job.meta else "",
        "uploads": [{"platform": u.platform, "ok": u.ok, "url": u.url or "", "error": u.error or ""}
                    for u in job.uploads.values()],
        "error": job.error or "",
        "lines": [scene.narration for scene in job.script.scenes] if job.script else [],
        "source": job.idea.source_text if job.idea else "",
        "review": (f"{job.reviews[-1].score}/10" if job.reviews else ""),
        "date": job.created_at.astimezone().strftime("%d.%m %H:%M"),
    }


def notes_view(settings) -> list[dict]:
    from .notes import Notes

    return [{"id": note["id"], "text": note["text"][:400], "file": note.get("file", "")}
            for note in Notes(Path(settings.workspace), Path(settings.footage.library_dir)).fresh()]


def library_view(settings) -> dict:
    from .production.library import count_media

    folder = Path(settings.footage.library_dir)
    index = Path(settings.workspace) / "footage_cache" / "my_footage" / "index.json"
    try:
        studied = sum(1 for entry in json.loads(index.read_text(encoding="utf-8")).values()
                      if entry.get("description"))
    except (OSError, ValueError):
        studied = 0
    return {"folder": str(folder.resolve()), **count_media(folder), "studied": studied,
            "only": settings.footage.library_only}


def settings_view(settings) -> dict:
    rate = re.match(r"^([+-]?\d+)%$", settings.voice.rate.strip())
    return {
        "speed": int(rate.group(1)) if rate else 0,
        "voice": "male" if "Dmitry" in settings.voice.voice else "female",
        "length": settings.channel.video_length_seconds,
        "auto_publish": settings.publish.auto_publish,
        "show_scene_text": settings.subtitles.show_scene_text,
        "source": settings.channel.source,
        "words_per_second": words_per_second(settings.channel),
    }


def connections(settings) -> dict:
    from .publishers import is_configured
    from .threads import ThreadsAuth

    result = {platform: is_configured(platform, settings) for platform in ("instagram", "youtube", "tiktok")}
    result["threads"] = ThreadsAuth(settings.secrets).is_configured()
    return result


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # noqa: S606 - открыть папку или таблицу в Windows
    else:
        log.info("Открыть: %s", path)


# --- HTTP ---


def make_handler(app: DesktopApp):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # без строки в консоли на каждый запрос
            pass

        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            # Защита от «перепривязки DNS»: страница чужого сайта не сможет выдать себя за нашу.
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self) -> None:
            if not self._host_ok():
                self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                page = PAGE.read_text(encoding="utf-8").replace("__TOKEN__", app.token)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/ping":
                self._json({"app": "video_agents"})
            elif path == "/api/state":
                if self.headers.get("X-Token") != app.token:
                    self._json({"error": "reload"}, HTTPStatus.FORBIDDEN)
                    return
                self._json(app.state())
            elif path.startswith("/video/"):
                self._video(path.removeprefix("/video/"))
            else:
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

        def do_POST(self) -> None:
            if not self._host_ok() or self.headers.get("X-Token") != app.token:
                self._json({"error": "Обновите страницу"}, HTTPStatus.FORBIDDEN)
                return
            name = self.path.removeprefix("/api/")
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}") if length else {}
                self._json({"message": app.action(name, data)})
            except Exception as exc:
                log.warning("Действие %s: %s", name, exc)
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def _video(self, job_id: str) -> None:
            from .storage import JobStore

            if not JOB_ID.match(job_id):
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                return
            try:
                job = JobStore(app.settings().workspace).load(job_id)
            except FileNotFoundError:
                job = None
            video = Path(job.video_path) if job and job.video_path else None
            if not video or not video.exists():
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                return
            size = video.stat().st_size
            start, end = 0, size - 1
            match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if match and (match.group(1) or match.group(2)):
                if match.group(1):
                    start = int(match.group(1))
                    end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
                else:
                    start = max(0, size - int(match.group(2)))
                if start > end:
                    self._send(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, b"", "video/mp4",
                               {"Content-Range": f"bytes */{size}"})
                    return
            with open(video, "rb") as fh:
                fh.seek(start)
                body = fh.read(end - start + 1)
            partial = match is not None and (match.group(1) or match.group(2))
            extra = {"Accept-Ranges": "bytes"}
            if partial:
                extra["Content-Range"] = f"bytes {start}-{end}/{size}"
            self._send(HTTPStatus.PARTIAL_CONTENT if partial else 200, body, "video/mp4", extra)

        do_HEAD = do_GET

    return Handler


def already_running(port: int) -> bool:
    try:
        return requests.get(f"http://127.0.0.1:{port}/api/ping", timeout=2).json().get("app") == "video_agents"
    except (requests.RequestException, ValueError):
        return False


def serve(config_path: str = "config.yaml", port: int = PORT, open_browser: bool = True) -> int:
    """Запускает окно программы; если оно уже запущено - просто открывает его в браузере."""
    url = f"http://127.0.0.1:{port}/"
    if already_running(port):
        if open_browser:
            webbrowser.open(url)
        return 0
    app = DesktopApp(Path(config_path))
    logging.getLogger().addHandler(_TaskLog(app.tasks))
    settings = app.settings()
    log_file = Path(settings.workspace) / "app.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    server.daemon_threads = True
    threading.Thread(target=app.auto_update_loop, args=(server,), daemon=True).start()
    threading.Thread(target=app.daily_loop, daemon=True).start()
    log.info("Окно программы: %s", url)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    if app.restart_requested:
        # Новая версия: запускаем себя заново, страница в браузере сама переподключится.
        subprocess.Popen([sys.executable, "-m", "video_agents", "--config", config_path, "app", "--no-browser"],
                         cwd=ROOT)
    return 0


def install_autostart(config_path: str = "config.yaml") -> Path | None:
    """Окно программы запускается вместе с Windows (без браузера) - чтобы ролик дня делался сам."""
    return install_shortcut(config_path, folder="Startup", name="Видео-агент (ролик дня)", extra=" --no-browser")


def install_shortcut(config_path: str = "config.yaml", folder: str = "Desktop", name: str = SHORTCUT_NAME,
                     extra: str = "") -> Path | None:
    """Ярлык «Видео-агент» на рабочем столе: открывает окно программы без чёрного окна консоли.

    Сбой здесь не мешает работе: программа откроется и без ярлыка.
    """
    if not IS_WINDOWS:
        return None
    scripts = Path(sys.executable).parent
    target = scripts / "pythonw.exe"
    if not target.exists():
        target = Path(sys.executable)
    config = str(Path(config_path).resolve())
    script = (
        # Путь к рабочему столу может быть с кириллицей: просим PowerShell отвечать в UTF-8.
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        f"$desktop = [Environment]::GetFolderPath('{folder}');"
        f"$link = Join-Path $desktop '{_ps(name)}.lnk';"
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($link);"
        f"$s.TargetPath = '{_ps(str(target))}';"
        f"$s.Arguments = '-m video_agents --config \"{_ps(config)}\" app{extra}';"
        f"$s.WorkingDirectory = '{_ps(str(ROOT))}';"
        "$s.IconLocation = 'shell32.dll,115';"
        "$s.Description = 'Ролики: сценарии, монтаж, публикация';"
        "$s.Save();"
        "Write-Output $link"
    )
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                                **NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Не удалось создать ярлык: %s", exc)
        return None
    if result.returncode != 0:
        log.warning("Не удалось создать ярлык: %s", (result.stderr or "").strip())
        return None
    lines = (result.stdout or "").strip().splitlines()
    return Path(lines[-1].strip()) if lines else Path(name + ".lnk")


def _ps(text: str) -> str:
    """Строка для PowerShell в одинарных кавычках."""
    return text.replace("'", "''")
