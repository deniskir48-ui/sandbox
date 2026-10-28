from video_agents.config import SubtitleConfig
from video_agents.production.subtitles import ass_time, build_ass, group_words, hex_to_ass
from video_agents.production.tts import Word, words_from_characters
from video_agents.publishers.tiktok import CHUNK, chunk_plan


def test_hex_to_ass():
    assert hex_to_ass("#FFD700") == "&H0000D7FF"


def test_ass_time():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(61.234) == "0:01:01.23"
    assert ass_time(3725.5) == "1:02:05.50"


def test_group_words_splits_on_count_pause_and_sentence_end():
    words = [Word("раз", 0, 0.2), Word("два", 0.2, 0.4), Word("три.", 0.4, 0.6),
             Word("четыре", 0.6, 0.8), Word("пять", 2.0, 2.2)]
    groups = group_words(words, max_words=3)
    assert [[w.text for w in g] for g in groups] == [["раз", "два", "три."], ["четыре"], ["пять"]]


def test_build_ass_highlights_each_word():
    words = [Word("привет", 0, 0.5), Word("мир", 0.5, 1.0)]
    ass = build_ass(words, SubtitleConfig(), 1080, 1920, captions=[(0, 1, "Заголовок")])
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue")]
    assert len(dialogue) == 3
    assert "Caption,,0,0,0,,Заголовок" in dialogue[0]
    assert "&H0000D7FF}ПРИВЕТ" in dialogue[1]
    assert "&H0000D7FF}МИР" in dialogue[2]


def test_words_from_characters():
    chars = list("да нет")
    starts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    words = words_from_characters(chars, starts, ends)
    assert [(w.text, w.start, w.end) for w in words] == [("да", 0.0, 0.2), ("нет", 0.3, 0.6)]


def test_tiktok_chunk_plan():
    assert chunk_plan(3_000_000) == (3_000_000, 1)
    size = CHUNK * 3 + 1234
    chunk_size, total = chunk_plan(size)
    assert (chunk_size, total) == (CHUNK, 3)  # остаток уходит в последний кусок


def test_pixabay_search_picks_large_or_medium(monkeypatch, tmp_path):
    from video_agents.production import footage

    hits = {"hits": [
        {"id": 1, "duration": 12, "videos": {"large": {"url": "https://x/1-large.mp4", "size": 20_000_000}}},
        {"id": 2, "duration": 30, "videos": {"large": {"url": "https://x/2-large.mp4", "size": 900_000_000},
                                             "medium": {"url": "https://x/2-medium.mp4", "size": 30_000_000}}},
        {"id": 3, "duration": 5, "videos": {"large": {"url": "", "size": 0}}},
    ]}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return hits

    calls = []
    monkeypatch.setattr(footage.requests, "get", lambda url, params, timeout: calls.append(params) or Response())
    clips = footage.PixabayFootage("KEY", tmp_path).search("woman running beach")
    assert [(c.id, c.url) for c in clips] == [(1, "https://x/1-large.mp4"), (2, "https://x/2-medium.mp4")]
    assert calls[0]["key"] == "KEY" and calls[0]["q"] == "woman running beach"


def test_make_footage_auto_prefers_available_key(tmp_path):
    from video_agents.config import FootageConfig, Secrets
    from video_agents.production.footage import PexelsFootage, PixabayFootage, make_footage

    auto = FootageConfig()
    assert isinstance(make_footage(auto, Secrets(pixabay_api_key="p"), tmp_path), PixabayFootage)
    assert isinstance(make_footage(auto, Secrets(pexels_api_key="x", pixabay_api_key="p"), tmp_path), PexelsFootage)
    assert make_footage(auto, Secrets(), tmp_path) is None
    assert make_footage(FootageConfig(provider="pexels"), Secrets(pixabay_api_key="p"), tmp_path) is None


def test_updater_overwrites_code_but_keeps_user_files(monkeypatch, tmp_path):
    import io
    import zipfile

    from video_agents import updater

    (tmp_path / "requirements.txt").write_text("x\n")
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / "video_agents").mkdir()
    (tmp_path / "video_agents" / "a.py").write_text("old")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("sandbox-main/requirements.txt", "x\n")
        z.writestr("sandbox-main/.env", "SECRET=from-github\n")
        z.writestr("sandbox-main/config.yaml", "x: 1\n")
        z.writestr("sandbox-main/video_agents/a.py", "new")
        z.writestr("sandbox-main/video_agents/b.py", "added")
        z.writestr("sandbox-main/../evil.py", "no")

    class Response:
        content = buf.getvalue()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(updater.requests, "get", lambda url, timeout: Response())
    changed = updater.update(tmp_path)
    assert sorted(changed) == ["video_agents/a.py", "video_agents/b.py"]
    assert (tmp_path / ".env").read_text() == "SECRET=1\n"
    assert not (tmp_path / "config.yaml").exists()
    assert not (tmp_path.parent / "evil.py").exists()


def test_word_budget_uses_target_and_ceiling():
    from video_agents.agents.brief import target_words, word_budget
    from video_agents.config import ChannelConfig

    channel = ChannelConfig()
    assert (target_words(channel), word_budget(channel)) == (25, 50)  # 10 с и потолок 20 с
    channel.max_video_length_seconds = 5  # потолок меньше цели - берём цель
    assert word_budget(channel) == 25


def test_instagram_auth_saves_and_refreshes_token(monkeypatch, tmp_path):
    import time

    from video_agents.config import InstagramConfig, Secrets
    from video_agents.publishers import instagram

    calls = []

    class Response:
        ok = True

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(url)
        if url.endswith("/me"):
            return Response({"user_id": 17841400000, "username": "fit.daily"})
        return Response({"access_token": "NEW", "expires_in": 5184000})

    monkeypatch.setattr(instagram.requests, "get", fake_get)
    secrets = Secrets(instagram_token_file=str(tmp_path / "ig.json"))
    auth = instagram.InstagramAuth(InstagramConfig(), secrets)
    assert not auth.is_configured()
    assert auth.save("OLD")["username"] == "fit.daily"
    assert auth.credentials() == ("OLD", "17841400000")  # свежий - не продлеваем

    monkeypatch.setattr(time, "time", lambda: 10**12)  # прошло много времени
    assert auth.credentials() == ("NEW", "17841400000")
    assert calls[-1] == "https://graph.instagram.com/refresh_access_token"


def test_ideas_ranked_by_relatability():
    from video_agents.agents.ideas import IdeaAgent
    from video_agents.config import ChannelConfig
    from video_agents.models import IdeaList, VideoIdea

    def idea(name, score):
        return VideoIdea(viewer_problem=name, relatability=score, topic=name, angle="a", hook="h", why_it_works="w")

    class LLM:
        def structured(self, **_):
            return IdeaList(ideas=[idea("creamer additive", 3), idea("belly fat", 9), idea("sore knees", 6),
                                   idea("no energy", 9)])

    ideas = IdeaAgent(LLM(), ChannelConfig(), web_research=False).generate(3, [])
    assert [i.topic for i in ideas] == ["belly fat", "no energy", "sore knees"]


def test_legacy_idea_loads():
    from video_agents.models import VideoIdea

    idea = VideoIdea.model_validate({"topic": "t", "angle": "a", "hook": "h", "why_it_works": "w"})
    assert (idea.viewer_problem, idea.relatability) == ("t", 0)


def test_parse_selection():
    from video_agents.cli import parse_selection

    assert parse_selection("", 5) == [0]
    assert parse_selection("все", 5) == [0, 1, 2, 3, 4]
    assert parse_selection("ALL", 3) == [0, 1, 2]
    assert parse_selection("1 3 5", 5) == [0, 2, 4]
    assert parse_selection("2-4", 5) == [1, 2, 3]
    assert parse_selection("5, 1, 5, 9", 5) == [4, 0]
    assert parse_selection("абв", 5) == [0]


class _HostResponse:
    def __init__(self, status, text="", payload=None):
        self.status_code, self.text, self.payload = status, text, payload
        self.ok = status < 400

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload


def test_instagram_login_publishes_by_temporary_url(monkeypatch, tmp_path):
    from video_agents.config import InstagramConfig, Secrets
    from video_agents.models import PlatformMeta
    from video_agents.publishers import instagram

    video = tmp_path / "final.mp4"
    video.write_bytes(b"fake mp4")
    calls = []

    def fake_post(url, headers=None, data=None, files=None, timeout=None, **kw):  # файлообменники
        calls.append(("host", url))
        assert "Mozilla" in headers["User-Agent"]
        if "uguu" in url:
            return _HostResponse(412, "<html><title>412 Precondition Failed</title></html>")
        return _HostResponse(200, "https://litter.catbox.moe/abc123.mp4\n")

    def fake_request(method, url, params=None, timeout=None, data=None):  # Instagram API
        path = url.split("/v23.0/")[1]
        calls.append((method, path, dict(data or {})))
        if path == "17841/media":
            return _HostResponse(200, payload={"id": "C1"})
        if path == "C1":
            return _HostResponse(200, payload={"status_code": "FINISHED"})
        if path == "17841/media_publish":
            return _HostResponse(200, payload={"id": "M1"})
        return _HostResponse(200, payload={"permalink": "https://www.instagram.com/reel/xyz/"})

    monkeypatch.setattr(instagram.requests, "post", fake_post)
    monkeypatch.setattr(instagram.requests, "request", fake_request)
    secrets = Secrets(instagram_access_token="T", instagram_user_id="17841", instagram_token_file=str(tmp_path / "x"))
    meta = PlatformMeta(youtube_title="t", youtube_description="d", youtube_tags=[], instagram_caption="Caption",
                        tiktok_caption="c")

    result = instagram.InstagramPublisher(InstagramConfig(), secrets).publish(video, meta)

    assert result.ok and result.url == "https://www.instagram.com/reel/xyz/"
    assert [c[1] for c in calls[:2]] == ["https://uguu.se/upload?output=text",
                                         "https://litterbox.catbox.moe/resources/internals/api.php"]
    method, path, data = calls[2]
    assert (method, path) == ("POST", "17841/media")
    assert data["video_url"] == "https://litter.catbox.moe/abc123.mp4" and "upload_type" not in data
    assert data["media_type"] == "REELS" and data["caption"] == "Caption"


def test_tmpfiles_link_is_converted_to_direct_download(monkeypatch, tmp_path):
    from video_agents.publishers import hosting

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(hosting.requests, "post", lambda *a, **k: _HostResponse(
        200, payload={"status": "success", "data": {"url": "http://tmpfiles.org/123/v.mp4"}}))
    assert hosting._tmpfiles(video) == "https://tmpfiles.org/dl/123/v.mp4"


def test_all_temporary_hosts_failing_is_reported_briefly(monkeypatch, tmp_path):
    import pytest

    from video_agents.publishers import hosting
    from video_agents.publishers.base import PublishError

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(hosting.requests, "post", lambda *a, **k: _HostResponse(
        412, "<html><head><title>412 Precondition Failed</title></head><body>nginx</body></html>"))
    with pytest.raises(PublishError) as error:
        hosting.upload_temporary(video)
    message = str(error.value)
    assert "uguu.se: HTTP 412" in message and "tmpfiles.org" in message and "<html>" not in message
