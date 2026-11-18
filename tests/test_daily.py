import re
from datetime import datetime, timezone

from test_library import make_media
from test_pipeline import FakeLLM, FakePublisher, FakeTTS

from video_agents.agents.planner import DailyPlan
from video_agents.config import Settings
from video_agents.daily_context import moon_phase, wind_name
from video_agents.notes import Notes
from video_agents.pipeline import Pipeline
from video_agents.production.library import make_library
from video_agents.production.render import VideoProducer


class PlannerLLM(FakeLLM):
    def __init__(self):
        super().__init__()
        self.plan_prompts = []

    def structured(self, *, output_model, prompt, **kw):
        if output_model is DailyPlan:
            self.plan_prompts.append(prompt)
            note = re.search(r"\[([0-9a-f]{8})\] Аптеки", prompt).group(1)
            number = next(int(n) for n, text in re.findall(r"^(\d+)\. (.+)$", prompt, re.M) if "аптека" in text)
            return DailyPlan(source="набросок", topic="Дежурные аптеки", viewer_problem="Живот скрутило вечером",
                             angle="Где искать дежурную", hook="У аптек на Кипре есть обед",
                             why_today="Сегодня среда - аптеки закрываются в обед",
                             material="Дежурные аптеки открыты до 23:00", media=[number, 99], note_ids=[note, "x"],
                             threads_post=0)
        name = getattr(output_model, "__name__", "")
        if name == "FileDescription":
            return output_model(description="аптека с зелёным крестом" if "фотография" in str(prompt) else "пляж")
        if name == "LibraryPicks":
            return output_model(picks=[1, 1])
        return super().structured(output_model=output_model, prompt=prompt, **kw)


def test_daily_video_from_own_footage_and_notes(tmp_path, monkeypatch):
    from video_agents import daily_context

    monkeypatch.setattr(daily_context, "weather", lambda lat, lon: "сегодня: ясно, ветер западный до 6 м/с")
    settings = Settings(workspace=str(tmp_path / "ws"))
    settings.video.width, settings.video.height, settings.video.fps = 360, 640, 15
    settings.video.music_dir = str(tmp_path / "no_music")
    settings.footage.library_dir = str(tmp_path / "my_footage")
    settings.footage.ai_images = "none"
    make_media(tmp_path / "my_footage")
    (tmp_path / "my_footage" / "идеи.txt").write_text("Про море зимой", encoding="utf-8")
    notes = Notes(tmp_path / "ws", tmp_path / "my_footage")
    note = notes.add("Аптеки: обед и выходные, дежурные до 23:00")

    llm = PlannerLLM()
    publishers = {"instagram": FakePublisher("instagram")}
    library = make_library(settings.footage, tmp_path / "ws" / "footage_cache", llm)
    pipeline = Pipeline(settings, llm=llm, producer=VideoProducer(settings, FakeTTS(), None, None, None, library),
                        publisher_factory=publishers.__getitem__,
                        platform_ready=lambda platform: platform == "instagram")

    job = pipeline.daily()

    prompt = llm.plan_prompts[0]
    assert "ветер западный" in prompt and "Луна:" in prompt  # день, погода и луна - в вводных
    assert "Про море зимой" in prompt and note["id"] in prompt  # наброски из окна и из файла
    assert job.status == "published" and job.idea.topic == "Дежурные аптеки"
    assert job.idea.footage_hint == ["trip/pharmacy.jpg — аптека с зелёным крестом"]
    assert "Дежурные аптеки открыты до 23:00" in job.idea.source_text and "обед и выходные" in job.idea.source_text
    # Использованный набросок больше не предлагается; текстовые файлы из папки - тоже наброски.
    assert [n["id"] for n in notes.fresh()] == ["file:notes.txt", "file:идеи.txt"]


def test_wind_and_moon():
    assert wind_name(0) == "северный" and wind_name(273) == "западный" and wind_name(350) == "северный"
    assert moon_phase(datetime(2000, 1, 6, 20, tzinfo=timezone.utc)) == "новолуние"
    assert moon_phase(datetime(2000, 1, 21, tzinfo=timezone.utc)) == "полнолуние"
