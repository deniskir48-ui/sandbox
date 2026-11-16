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


def test_threads_token_message_is_deleted_and_saved(bot, monkeypatch):
    from video_agents import threads

    bot.pipeline.settings.secrets.threads_token_file = str(bot.pipeline.store.root / "threads.json")
    monkeypatch.setattr(threads, "_get", lambda url, token, **p: {"id": "u1", "username": "denis.strength"})
    update = message("/threads SECRET-TOKEN")
    update["message"]["message_id"] = 77
    bot.handle(update)
    assert ("deleteMessage", {"chat_id": OWNER, "message_id": 77}, None) in bot.api.calls
    assert "Threads @denis.strength подключён" in bot.api.texts()[-1]


def test_threads_report_sends_summary_and_table(bot, monkeypatch):
    from video_agents import threads
    from video_agents.telegram.bot import THREADS

    posts = [{"id": "1", "text": "Belly fat myth", "views": 900}, {"id": "2", "text": "Protein", "views": 50}]
    monkeypatch.setattr(threads, "fetch_posts", lambda token: posts)
    monkeypatch.setattr(threads.ThreadsAuth, "token", lambda self: "T")
    bot.handle(message(THREADS))
    summary = bot.api.texts()[-1]
    assert "постов 2" in summary and summary.index("Belly fat myth") < summary.index("Protein")
    document = bot.api.calls[-1]
    assert document[0] == "sendDocument" and document[2]["document"][0] == "threads_posts.xlsx"


def test_trends_list_and_posts_buttons(bot, monkeypatch):
    from video_agents import threads
    from video_agents.telegram.bot import TRENDS

    monkeypatch.setattr(threads.ThreadsApp, "token", lambda self: "TH|1|2")
    monkeypatch.setattr(threads, "fetch_trends", lambda token, country: [
        {"title": "Ozempic and muscle loss", "description": "Debate", "trend_id": "987"}])
    monkeypatch.setattr(threads, "fetch_trend_posts", lambda token, trend_id: [
        {"username": "coach", "text": "Lift heavy on GLP-1", "permalink": "https://threads.com/x"}])

    bot.handle(message(TRENDS))
    trends_message = bot.api.sent()[-1]
    assert "1. Ozempic and muscle loss" in trends_message["text"]
    assert trends_message["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "tp:987"
    assert bot.pipeline.store.queue() == []  # тренды сами в очередь не попадают

    bot.handle(button("tp:987"))
    assert "@coach: Lift heavy on GLP-1" in bot.api.texts()[-1]


def test_threads_app_message_is_deleted(bot, monkeypatch):
    from video_agents import threads

    bot.pipeline.settings.secrets.threads_app_file = str(bot.pipeline.store.root / "app.json")
    monkeypatch.setattr(threads, "fetch_trends", lambda token, country: [{"title": "t", "trend_id": "1"}])
    update = message("/threads_app 123 SECRET")
    update["message"]["message_id"] = 88
    bot.handle(update)
    assert ("deleteMessage", {"chat_id": OWNER, "message_id": 88}, None) in bot.api.calls
    assert "Тренды подключены, сейчас их 1" in bot.api.texts()[-1]
    assert threads.ThreadsApp(bot.pipeline.settings.secrets).token() == "TH|123|SECRET"


def test_format_proposal_and_apply_with_voice(bot, monkeypatch, tmp_path):
    from test_reformat import PROPOSAL

    from video_agents import threads
    from video_agents.agents.channel_advisor import ChannelAdvisorAgent
    from video_agents.config import load_settings

    bot.config_path = tmp_path / "config.yaml"
    threads.save_posts([{"id": "1", "text": "Кипр", "views": 5}], bot.pipeline.store.root)
    monkeypatch.setattr(ChannelAdvisorAgent, "propose", lambda self, posts, hint, language, *a: PROPOSAL)

    bot.handle(message("/format Кипр и обзоры"))
    proposal_message = bot.api.sent()[-1]
    assert "Жизнь на Кипре" in proposal_message["text"]
    assert proposal_message["reply_markup"]["inline_keyboard"][1][0]["callback_data"] == "fa:female"

    bot.handle(button("fa:female"))
    assert "Формат канала обновлён" in bot.api.texts()[-1]
    assert load_settings(bot.config_path).voice.voice == "ru-RU-SvetlanaNeural"
    assert [i.topic for i in bot.pipeline.store.queue()] == PROPOSAL.example_topics

    bot.handle(button("fa:male"))  # повторное нажатие - предложение уже применено
    assert "устарело" in bot.api.texts()[-1]


def test_set_command_updates_file_and_running_settings(bot, tmp_path):
    from video_agents.config import load_settings

    bot.config_path = tmp_path / "config.yaml"
    bot.config_path.write_text("subtitles:\n  font: Arial\n", encoding="utf-8")
    bot.handle(message("/set subtitles.show_scene_text true"))
    assert "✅ subtitles.show_scene_text = True" in bot.api.texts()[-1]
    assert load_settings(bot.config_path).subtitles.show_scene_text is True
    assert bot.pipeline.settings.subtitles.show_scene_text is True
    bot.handle(message("/set subtitles.bogus 1"))
    assert bot.api.texts()[-1].startswith("❌")


def test_priorities_command(bot, tmp_path):
    from video_agents.config import load_settings

    bot.config_path = tmp_path / "config.yaml"
    bot.handle(message("/priorities\n1. Кипр: полезное, места\n2. Греческий\n- Спорт"))
    assert load_settings(bot.config_path).threads.priorities == ["Кипр: полезное, места", "Греческий", "Спорт"]
    assert bot.pipeline.settings.threads.priorities[0] == "Кипр: полезное, места"
    bot.handle(message("/priorities"))
    assert "1. Кипр: полезное, места" in bot.api.texts()[-1]
