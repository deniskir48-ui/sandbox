import threading
from http.server import ThreadingHTTPServer

import pytest
import requests
from test_pipeline import FakeLLM, FakePublisher, FakeTTS

from video_agents.config import load_settings
from video_agents.desktop import DesktopApp, make_handler, settings_view
from video_agents.pipeline import Pipeline
from video_agents.production.render import VideoProducer


@pytest.fixture
def app(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"workspace: {tmp_path / 'ws'}\n"
        "voice:\n  rate: '+8%'\n"
        f"video:\n  width: 360\n  height: 640\n  fps: 15\n  music_dir: {tmp_path / 'no_music'}\n",
        encoding="utf-8",
    )
    publishers = {"instagram": FakePublisher("instagram")}

    def pipeline():
        settings = load_settings(config)
        return Pipeline(settings, llm=FakeLLM(), producer=VideoProducer(settings, FakeTTS()),
                        publisher_factory=publishers.__getitem__,
                        platform_ready=lambda platform: platform == "instagram")

    app = DesktopApp(config, pipeline_factory=pipeline, sync=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield app
    server.shutdown()
    server.server_close()


def post(app, name, token=None, **data):
    return requests.post(f"{app.url}/api/{name}", json=data, headers={"X-Token": token or app.token}, timeout=60)


def state(app):
    return requests.get(f"{app.url}/api/state", headers={"X-Token": app.token}, timeout=10).json()


def test_page_carries_the_session_key(app):
    page = requests.get(app.url + "/", timeout=10)
    assert page.status_code == 200
    assert app.token in page.text and "Сделать ролик" in page.text


def test_actions_need_the_key_and_our_host(app):
    assert post(app, "queue_add", token="wrong", text="тема").status_code == 403
    # Чужое имя хоста (перепривязка DNS) - отказ, даже с правильным путём.
    response = requests.get(app.url + "/", headers={"Host": "evil.example:80"}, timeout=10)
    assert response.status_code == 403
    assert state(app)["queue"] == []


def test_make_video_then_publish_from_the_page(app):
    assert post(app, "make", topic="Как не сгореть на пляже в Лимассоле").status_code == 200
    jobs = state(app)["jobs"]
    assert len(jobs) == 1 and jobs[0]["status"] == "produced" and jobs[0]["has_video"]
    job_id = jobs[0]["id"]

    video = requests.get(f"{app.url}/video/{job_id}", timeout=10)
    assert video.status_code == 200 and video.headers["Content-Type"] == "video/mp4"
    part = requests.get(f"{app.url}/video/{job_id}", headers={"Range": "bytes=0-99"}, timeout=10)
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["Content-Range"].endswith(f"/{len(video.content)}")

    post(app, "publish", job=job_id)
    current = state(app)
    assert current["jobs"][0]["status"] == "published"
    assert any("опубликовано" in line["text"] for line in current["log"])


def test_bad_job_id_is_refused(app):
    assert post(app, "publish", job="../../secrets").status_code == 400
    assert requests.get(f"{app.url}/video/..%2Fsecrets", timeout=10).status_code == 404


def test_reject_hides_video(app):
    post(app, "make", topic="Тема")
    job_id = state(app)["jobs"][0]["id"]
    post(app, "reject", job=job_id)
    assert state(app)["jobs"] == []


def test_queue_add_and_remove(app):
    post(app, "queue_add", text="Первая")
    post(app, "queue_add", text="Вторая")
    queue = state(app)["queue"]
    assert [item["topic"] for item in queue] == ["Первая", "Вторая"]
    # Метка темы защищает от удаления не той темы, если очередь успела сдвинуться.
    assert "изменилась" in post(app, "queue_remove", index=0, tag=queue[1]["tag"]).json()["message"]
    post(app, "queue_remove", index=0, tag=queue[0]["tag"])
    assert [item["topic"] for item in state(app)["queue"]] == ["Вторая"]


def test_settings_change_config(app):
    post(app, "setting", key="speed", value=20)
    post(app, "setting", key="voice", value="male")
    post(app, "setting", key="length", value=30)
    post(app, "setting", key="auto_publish", value=True)
    settings = load_settings(app.config_path)
    assert settings.voice.rate == "+20%"
    assert settings.voice.voice == "ru-RU-DmitryNeural"
    assert settings.channel.video_length_seconds == 30
    assert settings.channel.max_video_length_seconds >= 30
    assert settings.publish.auto_publish is True
    view = state(app)["settings"]
    assert view["speed"] == 20 and view["voice"] == "male" and view["auto_publish"] is True
    assert post(app, "setting", key="secrets.x", value=1).status_code == 400


def test_speed_view_handles_negative_and_odd_values():
    settings = load_settings(None)
    settings.voice.rate = "-5%"
    assert settings_view(settings)["speed"] == -5
    settings.voice.rate = "fast"
    assert settings_view(settings)["speed"] == 0
