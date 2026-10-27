from pathlib import Path

import pytest

from video_agents.config import Settings
from video_agents.models import IdeaList, PlatformMeta, Review, Scene, Script, UploadResult, VideoIdea
from video_agents.pipeline import Pipeline
from video_agents.production.ffmpeg import probe_duration, run_ffmpeg
from video_agents.production.render import VideoProducer
from video_agents.production.tts import Speech, Word
from video_agents.publishers.base import Publisher


class FakeLLM:
    """Отвечает заготовками по типу запрошенной модели; первый сценарий редактор не пропускает."""

    def __init__(self):
        self.reviews = 0
        self.calls: list[str] = []

    def research(self, **_):
        return "Новость: найдена новая экзопланета."

    def structured(self, *, output_model, prompt, **_):
        self.calls.append(output_model.__name__)
        if output_model is IdeaList:
            return IdeaList(ideas=[
                VideoIdea(topic=f"Тема {i}", angle="угол", hook="хук", why_it_works="потому что")
                for i in range(5)
            ])
        if output_model is Script:
            return Script(
                title="Почему Венера крутится назад",
                scenes=[
                    Scene(narration="Венера вращается в обратную сторону.", visual_query="venus planet", on_screen_text="Венера"),
                    Scene(narration="Подпишись, чтобы узнать почему!", visual_query="night sky", on_screen_text=""),
                ],
                call_to_action="Подпишись",
            )
        if output_model is Review:
            self.reviews += 1
            approved = self.reviews > 1
            return Review(score=9 if approved else 5, approved=approved, strengths=["хук"],
                          problems=[] if approved else ["слабый финал"],
                          rewrite_instructions="" if approved else "усиль финал")
        if output_model is PlatformMeta:
            return PlatformMeta(youtube_title="Венера", youtube_description="Описание #space",
                                youtube_tags=["космос"], instagram_caption="Подпись", tiktok_caption="Подпись #space")
        raise AssertionError(output_model)


class FakeTTS:
    """Синус вместо голоса; слова равномерно распределены по длительности."""

    def synthesize(self, text: str, out_path: Path) -> Speech:
        duration = 0.4 * len(text.split())
        run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", str(out_path)])
        step = duration / len(text.split())
        words = [Word(w, i * step, (i + 1) * step) for i, w in enumerate(text.split())]
        return Speech(out_path, probe_duration(out_path), words)


class FakePublisher(Publisher):
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail
        self.calls = 0

    def publish(self, video_path, meta):
        self.calls += 1
        assert video_path.exists()
        if self.fail:
            raise RuntimeError("API недоступен")
        return UploadResult(platform=self.name, ok=True, id="123", url=f"https://{self.name}/123")


@pytest.fixture
def settings(tmp_path):
    s = Settings(workspace=str(tmp_path / "ws"))
    s.video.width, s.video.height, s.video.fps = 360, 640, 15  # быстрее в тестах
    s.video.music_dir = str(tmp_path / "no_music")
    s.llm.max_revisions = 2
    return s


def test_full_run_produces_video_and_publishes(settings):
    llm = FakeLLM()
    publishers = {"youtube": FakePublisher("youtube"), "instagram": FakePublisher("instagram"),
                  "tiktok": FakePublisher("tiktok", fail=True)}
    pipeline = Pipeline(settings, llm=llm, producer=VideoProducer(settings, FakeTTS()),
                        publisher_factory=publishers.__getitem__)

    [job] = pipeline.run(count=1, publish=True)

    assert job.idea.topic == "Тема 0"
    assert [r.approved for r in job.reviews] == [False, True]  # один круг правок
    assert llm.calls.count("Script") == 2
    video = Path(job.video_path)
    assert video.exists()
    assert job.duration == pytest.approx(probe_duration(video), abs=0.1)
    assert job.duration > 3.5
    assert job.uploads["youtube"].ok and job.uploads["instagram"].ok
    assert not job.uploads["tiktok"].ok and "API недоступен" in job.uploads["tiktok"].error
    assert job.status == "partially_published"

    # Повторная публикация не дублирует успешные загрузки.
    publishers["tiktok"].fail = False
    job = pipeline.publish(pipeline.store.load(job.id))
    assert publishers["youtube"].calls == 1
    assert publishers["tiktok"].calls == 2
    assert job.status == "published"

    ass = (video.parent / "subs.ass").read_text(encoding="utf-8")
    assert "ВЕНЕРА" in ass and "Caption" in ass


def test_past_topics_are_passed_to_idea_agent(settings):
    llm = FakeLLM()
    pipeline = Pipeline(settings, llm=llm, producer=VideoProducer(settings, FakeTTS()))
    pipeline.run(count=1, publish=False)
    assert pipeline.store.past_topics() == ["Тема 0"]


def test_failed_job_is_saved(settings):
    class BrokenProducer:
        def produce(self, script, job_dir):
            raise RuntimeError("ffmpeg сломался")

    pipeline = Pipeline(settings, llm=FakeLLM(), producer=BrokenProducer())
    [job] = pipeline.run(topic="Своя тема", publish=False)
    assert job.status == "failed"
    assert pipeline.store.load(job.id).error == "ffmpeg сломался"
