import time

import pytest
from test_pipeline import FakeLLM, FakePublisher, FakeTTS

from video_agents.config import Settings
from video_agents.models import manual_idea
from video_agents.pipeline import Pipeline
from video_agents.production.render import VideoProducer
from video_agents.telegram import setup
from video_agents.telegram.api import TelegramAccess, TelegramAPI
from video_agents.telegram.bot import IDEAS, MAKE, QUEUE, Bot, topic_tag
from video_agents.telegram.messages import notify_jobs

OWNER = 111


class FakeAPI(TelegramAPI):
    def __init__(self, updates=()):
        super().__init__("TOKEN")
        self.calls = []
        self.updates = list(updates)
        self.next_id = 0

    def call(self, method, files=None, http_timeout=60, **params):
        self.calls.append((method, params, files))
        if method == "getUpdates":
            return self.updates.pop(0) if self.updates else []
        if method == "getMe":
            return {"username": "denis_video_bot"}
        self.next_id += 1
        return {"message_id": self.next_id}

    def sent(self, method="sendMessage"):
        return [params for name, params, _ in self.calls if name == method]

    def texts(self):
        return [params.get("text") or params.get("caption") for name, params, _ in self.calls
                if name in ("sendMessage", "sendVideo")]


def message(text, chat=OWNER, age=0):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "date": time.time() - age, "text": text}}


def button(data, message_id=50):
    return {"update_id": 2, "callback_query": {"id": "q", "data": data,
                                               "message": {"message_id": message_id, "chat": {"id": OWNER}}}}


@pytest.fixture
def bot(tmp_path):
    settings = Settings(workspace=str(tmp_path / "ws"))
    settings.video.width, settings.video.height, settings.video.fps = 360, 640, 15
    settings.video.music_dir = str(tmp_path / "no_music")
    publishers = {"instagram": FakePublisher("instagram")}
    pipeline = Pipeline(settings, llm=FakeLLM(), producer=VideoProducer(settings, FakeTTS()),
                        publisher_factory=publishers.__getitem__,
                        platform_ready=lambda platform: platform == "instagram")
    api = FakeAPI()
    instance = Bot(api, OWNER, pipeline, sync=True)
    instance.publishers = publishers
    return instance


def test_strangers_and_stale_messages_are_ignored(bot):
    bot.handle(message("hack me", chat=999))
    bot.handle(message("old topic", age=3600))
    assert bot.api.calls == []
    assert bot.pipeline.store.queue() == []


def test_free_text_becomes_queued_topic(bot):
    bot.handle(message("Why you can't do pull-ups"))
    assert [i.topic for i in bot.pipeline.store.queue()] == ["Why you can't do pull-ups"]
    assert "добавлена в очередь (№1)" in bot.api.texts()[-1]


def test_ideas_buttons_fill_the_queue(bot):
    bot.handle(message(IDEAS))
    ideas_message = bot.api.sent()[-1]
    assert "1. Тема 0" in ideas_message["text"]
    batch = next(iter(bot.idea_batches))

    bot.handle(button(f"i:{batch}:1"))
    assert [i.topic for i in bot.pipeline.store.queue()] == ["Тема 1"]
    markup = bot.api.sent("editMessageReplyMarkup")[-1]["reply_markup"]
    assert markup["inline_keyboard"][0][1]["text"] == "✅ 2"

    bot.handle(button(f"ia:{batch}"))  # «все» не дублирует уже добавленную
    assert [i.topic for i in bot.pipeline.store.queue()] == ["Тема 1", "Тема 0", "Тема 2", "Тема 3", "Тема 4"]


def test_make_review_and_publish(bot):
    bot.pipeline.enqueue([manual_idea("Squat depth")])
    bot.handle(message(MAKE))
    video = bot.api.sent("sendVideo")[-1]
    job_id = video["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":", 1)[1]
    assert "Squat depth" in video["caption"]
    assert bot.pipeline.store.load(job_id).status == "produced"

    bot.handle(button(f"p:{job_id}"))
    assert bot.publishers["instagram"].calls == 1
    assert bot.pipeline.store.load(job_id).status == "published"
    assert "✅ Instagram: https://instagram/123" in bot.api.texts()[-1]
    # статус «⏳ ...» удаляется после работы
    assert bot.api.sent("deleteMessage")


def test_reject_marks_job(bot):
    bot.handle(message(MAKE))
    job_id = bot.api.sent("sendVideo")[-1]["reply_markup"]["inline_keyboard"][0][2]["callback_data"][2:]
    bot.handle(button(f"d:{job_id}"))
    assert bot.pipeline.store.load(job_id).status == "rejected"


def test_queue_removal_checks_topic(bot):
    bot.pipeline.enqueue([manual_idea("A"), manual_idea("B")])
    bot.handle(message(QUEUE))
    bot.handle(button(f"qd:0:{topic_tag('B')}"))  # очередь «сдвинулась» - не удаляем
    assert [i.topic for i in bot.pipeline.store.queue()] == ["A", "B"]
    bot.handle(button(f"qd:1:{topic_tag('B')}"))
    assert [i.topic for i in bot.pipeline.store.queue()] == ["A"]


def test_task_errors_are_reported(bot):
    class Broken:
        def produce(self, script, job_dir):
            raise RuntimeError("ffmpeg сломался")

    bot.pipeline._producer = Broken()
    bot.handle(message(MAKE))
    assert "Ролик не получился" in bot.api.texts()[-1] and "ffmpeg сломался" in bot.api.texts()[-1]


def test_notify_jobs_sends_videos_from_scheduled_runs(bot, monkeypatch):
    settings = bot.pipeline.settings
    settings.secrets.telegram_file = str(bot.pipeline.store.root / "telegram.json")
    TelegramAccess("TOKEN", OWNER).save(settings.secrets)
    api = FakeAPI()
    monkeypatch.setattr("video_agents.telegram.messages.TelegramAPI", lambda token: api)

    [job] = bot.pipeline.run(topic="Scheduled", publish=True)
    notify_jobs(settings, [job])
    assert "Scheduled" in api.sent("sendVideo")[-1]["caption"]
    assert api.sent("sendVideo")[-1]["reply_markup"] is None  # уже опубликован - кнопки не нужны


def test_pairing_waits_for_code(tmp_path):
    api = FakeAPI(updates=[
        [{"update_id": 5, "message": {"chat": {"id": 7}, "text": "/start 0000"}}],
        [{"update_id": 6, "message": {"chat": {"id": OWNER}, "text": "/start 4821"}}],
    ])
    assert setup.pair(api, "4821", wait_seconds=5) == OWNER


def test_connect_saves_access(tmp_path, monkeypatch):
    from video_agents.config import Secrets

    api = FakeAPI(updates=[[{"update_id": 1, "message": {"chat": {"id": OWNER}, "text": "/start 1234"}}]])
    monkeypatch.setattr(setup, "TelegramAPI", lambda token: api)
    secrets = Secrets(telegram_file=str(tmp_path / "tg.json"))
    setup.connect("TOKEN", secrets, code="1234", ask=lambda text: None)
    assert TelegramAccess.load(secrets) == TelegramAccess("TOKEN", OWNER)
    assert "Бот подключён" in api.texts()[-1]


def test_second_bot_instance_exits_on_conflict(bot):
    from video_agents.telegram.api import TelegramError

    def conflict(method, files=None, http_timeout=60, **params):
        if method == "getUpdates":
            raise TelegramError("Conflict: terminated by other getUpdates request", 409)
        return {"message_id": 1}

    bot.api.call = conflict
    bot.run_forever()  # не зависает: завершается сам
