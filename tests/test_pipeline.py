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
                    Scene(narration="Венера вращается в обратную сторону.", visual_queries=["venus planet"], on_screen_text="Венера"),
                    Scene(narration="Подпишись, чтобы узнать почему!", visual_queries=["night sky", "stars"], on_screen_text=""),
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


SYSTEM_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


@pytest.mark.skipif(not SYSTEM_FONT.exists(), reason="нет системного шрифта DejaVu")
def test_render_with_custom_fonts_dir(settings, tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / SYSTEM_FONT.name).write_bytes(SYSTEM_FONT.read_bytes())
    settings.video.fonts_dir = str(fonts)
    script = FakeLLM().structured(output_model=Script, prompt="")
    result = VideoProducer(settings, FakeTTS()).produce(script, tmp_path / "job")
    assert result.video_path.exists()


@pytest.mark.skipif(not SYSTEM_FONT.exists(), reason="нет системного шрифта DejaVu")
def test_windows_copies_system_arial(settings, tmp_path, monkeypatch):
    from video_agents.production import render

    windir = tmp_path / "Windows"
    (windir / "Fonts").mkdir(parents=True)
    (windir / "Fonts" / "arialbd.ttf").write_bytes(SYSTEM_FONT.read_bytes())
    monkeypatch.setenv("WINDIR", str(windir))
    monkeypatch.setattr(render, "IS_WINDOWS", True)
    settings.video.fonts_dir = str(tmp_path / "no_fonts")
    script = FakeLLM().structured(output_model=Script, prompt="")
    result = VideoProducer(settings, FakeTTS()).produce(script, tmp_path / "job")
    assert result.video_path.exists()
    assert [p.name for p in (tmp_path / "job" / "fonts").iterdir()] == ["arialbd.ttf"]


def test_legacy_visual_query_is_loaded():
    scene = Scene.model_validate({"narration": "x", "visual_query": "gym", "on_screen_text": ""})
    assert scene.visual_queries == ["gym"]


def test_long_script_is_shortened(settings):
    class LongLLM(FakeLLM):
        def structured(self, *, output_model, prompt, **kw):
            if output_model is Script and "Сократи" not in prompt:
                self.calls.append("Script")
                long_text = " ".join(["word"] * 200)
                return Script(title="t", call_to_action="c",
                              scenes=[Scene(narration=long_text, visual_queries=["gym"], on_screen_text="")])
            if output_model is Script:
                self.calls.append("Shorten")
            return super().structured(output_model=output_model, prompt=prompt, **kw)

    settings.channel.video_length_seconds = 10
    settings.channel.max_video_length_seconds = 30  # максимум 75 слов
    llm = LongLLM()
    pipeline = Pipeline(settings, llm=llm, producer=VideoProducer(settings, FakeTTS()))
    [job] = pipeline.run(topic="Тема", publish=False)
    assert "Shorten" in llm.calls
    assert len(job.script.full_text.split()) <= 75


class FakeFootage:
    def __init__(self, results):
        self.results = results  # запрос -> список Clip
        self.downloaded = []

    def search(self, query):
        return self.results.get(query, [])

    def preview(self, clip):
        return b"\xff\xd8 fake jpeg " + str(clip.id).encode()

    def download(self, clip):
        self.downloaded.append(clip.id)
        path = Path(self._dir) / f"{clip.id}.mp4"
        run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=1", "-pix_fmt", "yuv420p", str(path)])
        return path


class FakeEditor:
    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    def choose(self, narration, title, previews, relaxed=False):
        self.seen.append((len(previews), relaxed))
        return self.answers.pop(0)


def test_editor_rejects_first_query_and_picks_from_second(settings, tmp_path):
    from video_agents.production.footage import Clip

    footage = FakeFootage({
        "venus planet": [Clip(1, 10, "u1"), Clip(2, 10, "u2")],
        "night sky": [Clip(3, 10, "u3"), Clip(4, 10, "u4")],
    })
    footage._dir = tmp_path
    editor = FakeEditor([1, None, 1])  # сцена 1: вариант 2; сцена 2: «night sky» отклонён, из «stars» нет
    footage.results["stars"] = [Clip(5, 10, "u5"), Clip(6, 10, "u6")]
    script = FakeLLM().structured(output_model=Script, prompt="")
    VideoProducer(settings, FakeTTS(), footage, editor).produce(script, tmp_path / "job")
    assert footage.downloaded == [2, 6]
    assert editor.seen == [(2, False), (2, False), (2, False)]


def test_without_editor_takes_first_long_enough(settings, tmp_path):
    from video_agents.production.footage import Clip

    footage = FakeFootage({"venus planet": [Clip(1, 0.5, "u1"), Clip(2, 30, "u2"), Clip(3, 60, "u3")],
                           "night sky": [Clip(4, 30, "u4")]})
    footage._dir = tmp_path
    script = FakeLLM().structured(output_model=Script, prompt="")
    VideoProducer(settings, FakeTTS(), footage).produce(script, tmp_path / "job")
    assert footage.downloaded == [2, 4]  # релевантность важнее длины, слишком короткие пропускаем


def _two_scene_script(backup=()):
    script = FakeLLM().structured(output_model=Script, prompt="")
    return script.model_copy(update={"backup_queries": list(backup)})


def test_backup_queries_then_relaxed_pass(settings, tmp_path):
    from video_agents.production.footage import Clip

    footage = FakeFootage({
        "venus planet": [Clip(1, 10, "u1"), Clip(2, 10, "u2"), Clip(3, 10, "u3")],
        "night sky": [Clip(4, 10, "u4")],
        "stars": [],
        "space": [Clip(7, 10, "u7"), Clip(8, 10, "u8")],
    })
    footage._dir = tmp_path
    # Сцена 1: точный кадр не найден ни по запросу сцены, ни по общему -> мягкий проход берёт №2 из пула.
    # Сцена 2: «night sky» отклонён, общий запрос «space» подошёл: индекс 0 - клип 7.
    editor = FakeEditor([None, None, 1, None, 0])
    VideoProducer(settings, FakeTTS(), footage, editor).produce(_two_scene_script(["space"]), tmp_path / "job")
    assert editor.seen == [(3, False), (2, False), (4, True), (1, False), (2, False)]
    assert footage.downloaded == [2, 7]


def test_nothing_fits_continues_previous_scene(settings, tmp_path):
    from video_agents.production import render
    from video_agents.production.footage import Clip

    footage = FakeFootage({"venus planet": [Clip(1, 10, "u1")], "night sky": [Clip(2, 10, "u2")]})
    footage._dir = tmp_path
    editor = FakeEditor([0, None, None, None])  # сцена 1: берём вариант 1; сцена 2: ничего не подходит
    plans = []
    original = render.VideoProducer._render_scene
    monkey = lambda self, plan, *a: plans.append(plan) or original(self, plan, *a)
    render.VideoProducer._render_scene = monkey
    try:
        VideoProducer(settings, FakeTTS(), footage, editor).produce(_two_scene_script(), tmp_path / "job")
    finally:
        render.VideoProducer._render_scene = original
    assert footage.downloaded == [1]  # помаду (клип 2) не скачиваем
    assert plans[1].path == plans[0].path and plans[1].start > 0  # продолжение кадра с того же места


def test_detect_black_borders(tmp_path):
    from video_agents.production.ffmpeg import detect_black_borders

    boxed = tmp_path / "boxed.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=400x360:r=15:d=4", "-vf", "pad=640:360:0:0:black",
                "-pix_fmt", "yuv420p", str(boxed)])
    crop = detect_black_borders(boxed)
    assert crop and crop.startswith("crop=400:360")
    plain = tmp_path / "plain.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=4", "-pix_fmt", "yuv420p", str(plain)])
    assert detect_black_borders(plain) is None


def test_unconfigured_platforms_are_skipped(settings):
    publishers = {"youtube": FakePublisher("youtube"), "instagram": FakePublisher("instagram"),
                  "tiktok": FakePublisher("tiktok")}
    pipeline = Pipeline(settings, llm=FakeLLM(), producer=VideoProducer(settings, FakeTTS()),
                        publisher_factory=publishers.__getitem__,
                        platform_ready=lambda platform: platform == "instagram")
    [job] = pipeline.run(topic="Тема", publish=True)
    assert list(job.uploads) == ["instagram"]
    assert job.status == "published"
    assert publishers["youtube"].calls == publishers["tiktok"].calls == 0

    # Явно запрошенная, но не подключённая площадка - пробуем и сообщаем об ошибке, а не молчим.
    job = pipeline.publish(job, ["youtube"])
    assert publishers["youtube"].calls == 1


def test_run_with_chosen_idea_skips_idea_generation(settings):
    llm = FakeLLM()
    pipeline = Pipeline(settings, llm=llm, producer=VideoProducer(settings, FakeTTS()))
    chosen = VideoIdea(viewer_problem="I can't lose belly fat", relatability=9, topic="Belly fat",
                       angle="a", hook="h", why_it_works="w")
    [job] = pipeline.run(ideas=[chosen], publish=False)
    assert job.idea.topic == "Belly fat"
    assert "IdeaList" not in llm.calls


def test_queue_is_used_before_new_ideas(settings):
    llm = FakeLLM()
    pipeline = Pipeline(settings, llm=llm, producer=VideoProducer(settings, FakeTTS()))
    queued = [VideoIdea(viewer_problem=f"p{i}", relatability=9, topic=f"Очередь {i}", angle="a", hook="h",
                        why_it_works="w") for i in range(3)]
    pipeline.enqueue(queued)
    assert "Очередь 1" in pipeline.store.past_topics()  # очередь не предлагается повторно

    jobs = pipeline.run(count=2, publish=False)
    assert [j.idea.topic for j in jobs] == ["Очередь 0", "Очередь 1"]
    assert [i.topic for i in pipeline.store.queue()] == ["Очередь 2"]
    assert "IdeaList" not in llm.calls

    jobs = pipeline.run(count=2, publish=False)  # 1 из очереди + 1 новая
    assert [j.idea.topic for j in jobs] == ["Очередь 2", "Тема 0"]
    assert pipeline.store.queue() == []


def test_failed_queued_idea_goes_back_to_queue(settings):
    class BrokenProducer:
        def produce(self, script, job_dir):
            raise RuntimeError("сбой")

    pipeline = Pipeline(settings, llm=FakeLLM(), producer=BrokenProducer())
    pipeline.enqueue([VideoIdea(viewer_problem="p", relatability=9, topic="Важная тема", angle="a", hook="h",
                                why_it_works="w")])
    [job] = pipeline.run(publish=False)
    assert job.status == "failed"
    assert [i.topic for i in pipeline.store.queue()] == ["Важная тема"]


def test_generated_ideas_are_logged(settings):
    import json

    pipeline = Pipeline(settings, llm=FakeLLM(), producer=VideoProducer(settings, FakeTTS()))
    pipeline.ideas(3)
    lines = pipeline.store.ideas_log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["idea"]["topic"] for line in lines] == ["Тема 0", "Тема 1", "Тема 2"]


def test_queue_cli_add_remove_clear(tmp_path, monkeypatch, capsys):
    from video_agents import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    (tmp_path / "config.yaml").write_text("workspace: ws\n", encoding="utf-8")
    cli.main(["queue", "add", "Why crunches won't give you abs", "Best time to train"])
    cli.main(["queue", "add", "Protein myths"])
    cli.main(["queue", "remove", "2"])
    out = capsys.readouterr().out.split("Why crunches won't give you abs")[-1]  # вывод после последней команды
    assert "2. Protein myths" in out and "Best time to train" not in out
    from video_agents.storage import JobStore
    assert [i.topic for i in JobStore(tmp_path / "ws").queue()] == ["Why crunches won't give you abs", "Protein myths"]
    cli.main(["queue", "clear"])
    assert JobStore(tmp_path / "ws").queue() == []
