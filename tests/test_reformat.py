from pathlib import Path

from test_pipeline import FakeLLM, FakeTTS

from video_agents.agents.channel_advisor import ChannelAdvisorAgent, ChannelProposal, proposal_text
from video_agents.config import Settings, load_settings
from video_agents.models import manual_idea
from video_agents.pipeline import Pipeline
from video_agents.production.render import VideoProducer
from video_agents.reformat import VOICES, apply_proposal, write_config

PROPOSAL = ChannelProposal(
    niche="Жизнь на Кипре глазами переехавшего: быт, цены, лайфхаки и честные обзоры",
    audience="Русскоязычные на Кипре и те, кто думает о переезде",
    tone="Личный опыт, с иронией, по делу",
    video_length_seconds=20,
    max_video_length_seconds=40,
    extra_rules=["Без спойлеров в обзорах", "Цены - только проверенные"],
    disclaimer="",
    example_topics=["Сколько стоит жизнь в Лимассоле", "3 ошибки при аренде квартиры на Кипре"],
    reasoning="Лучше всего заходят посты про быт и деньги",
)

CONFIG = """# Мой канал
channel:
  niche: "Fitness"      # старая ниша
  language: "en"
  video_length_seconds: 10
  extra_rules:
    - "Do not mention brands"
llm:
  model: claude-opus-5-5  # главная модель
voice:
  provider: edge
  voice: en-US-AndrewMultilingualNeural
  rate: "+5%"
"""


def test_write_config_keeps_comments_and_other_settings(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    write_config(path, PROPOSAL, "ru", VOICES["female"][1])
    text = path.read_text(encoding="utf-8")
    assert "# Мой канал" in text and "# главная модель" in text
    settings = load_settings(path)
    assert settings.channel.niche.startswith("Жизнь на Кипре") and settings.channel.language == "ru"
    assert settings.channel.extra_rules == PROPOSAL.extra_rules
    assert (settings.channel.video_length_seconds, settings.channel.max_video_length_seconds) == (20, 40)
    assert settings.voice.voice == "ru-RU-SvetlanaNeural" and settings.voice.rate == "+5%"
    assert settings.llm.model == "claude-opus-5-5"


def test_apply_proposal_updates_running_pipeline_and_queue(tmp_path):
    settings = Settings(workspace=str(tmp_path / "ws"))
    pipeline = Pipeline(settings, llm=FakeLLM(), producer=VideoProducer(settings, FakeTTS()))
    pipeline.enqueue([manual_idea("Old fitness topic")])
    removed = apply_proposal(pipeline, tmp_path / "config.yaml", PROPOSAL, "ru", VOICES["male"][1])

    assert removed == 1
    assert [i.topic for i in pipeline.store.queue()] == PROPOSAL.example_topics
    assert "Old fitness topic" in (pipeline.store.root / "ideas_queue.backup.json").read_text(encoding="utf-8")
    assert pipeline.writer.channel.niche == PROPOSAL.niche  # агенты видят новый формат без перезапуска
    assert pipeline.settings.voice.voice == "ru-RU-DmitryNeural" and pipeline._producer is None
    assert load_settings(tmp_path / "config.yaml").channel.language == "ru"


def test_advisor_sends_best_posts_and_hint():
    seen = {}

    class LLM:
        def structured(self, *, prompt, output_model, **kw):
            seen["prompt"] = prompt
            return PROPOSAL

    posts = [{"id": str(i), "text": f"post {i}", "views": i} for i in range(40)]
    result = ChannelAdvisorAgent(LLM()).propose(posts, "Кипр, книги, игры")
    assert result is PROPOSAL
    assert "Кипр, книги, игры" in seen["prompt"] and "post 39" in seen["prompt"]
    assert "Сколько стоит жизнь в Лимассоле" in proposal_text(PROPOSAL)


def test_cli_channel_from_threads(tmp_path, monkeypatch, capsys):
    from video_agents import cli, threads

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    Path("config.yaml").write_text(CONFIG + "workspace: ws\n", encoding="utf-8")
    threads.save_posts([{"id": "1", "text": "Аренда на Кипре", "views": 900}], Path("ws"))
    monkeypatch.setattr(ChannelAdvisorAgent, "propose", lambda self, posts, hint, language, all_topics: PROPOSAL)
    answers = iter(["2", "да"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.main(["channel", "from-threads", "--hint", "Кипр", "--all-topics"]) == 0
    assert "Сколько стоит жизнь в Лимассоле" in capsys.readouterr().out
    settings = load_settings("config.yaml")
    assert settings.channel.language == "ru" and settings.voice.voice == "ru-RU-SvetlanaNeural"
    assert settings.threads.topic_filter is False  # «все темы» - отборщик не режет по теме
    from video_agents.storage import JobStore

    assert JobStore("ws").queue() == []  # ролики пойдут из постов - темы агента в очередь не ставим


def test_set_value_changes_one_setting_and_validates(tmp_path):
    import pytest

    from video_agents.config_edit import ConfigEditError, apply_to, set_value

    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    assert set_value(path, "subtitles.show_scene_text", "true") is True
    assert set_value(path, "llm.max_revisions", "1") == 1
    text = path.read_text(encoding="utf-8")
    assert "# главная модель" in text
    settings = load_settings(path)
    assert settings.subtitles.show_scene_text is True and settings.llm.max_revisions == 1

    with pytest.raises(ConfigEditError):
        set_value(path, "llm.max_revisions", "много")
    with pytest.raises(ConfigEditError):
        set_value(path, "voice.no_such_field", "1")
    assert path.read_text(encoding="utf-8") == text  # при ошибке файл не испорчен

    live = Settings()
    apply_to(live, "subtitles.show_scene_text", True)
    assert live.subtitles.show_scene_text is True



def test_advisor_all_topics_mode_asks_for_blog_format():
    seen = {}

    class LLM:
        def structured(self, *, prompt, **kw):
            seen["prompt"] = prompt
            return PROPOSAL

    ChannelAdvisorAgent(LLM()).propose([{"id": "1", "text": "x", "views": 1}], all_topics=True)
    assert "ничего не исключай" in seen["prompt"] and "афиши" in seen["prompt"]


def test_screener_without_topic_filter_does_not_mention_topic_rule():
    from video_agents.agents.post_screener import PostScreenerAgent, Screening
    from video_agents.config import ChannelConfig

    systems = []

    class LLM:
        def structured(self, *, system, **kw):
            systems.append(system)
            return Screening(verdicts=[])

    PostScreenerAgent(LLM(), ChannelConfig(), topic_filter=False).screen([{"id": "1", "text": "t"}])
    PostScreenerAgent(LLM(), ChannelConfig(), topic_filter=True).screen([{"id": "1", "text": "t"}])
    assert "не по теме" not in systems[0] and "не по теме" in systems[1]
