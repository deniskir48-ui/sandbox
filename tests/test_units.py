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
