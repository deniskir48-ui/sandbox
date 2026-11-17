import struct

from test_pipeline import FakeTTS, _two_scene_script

from video_agents.config import Settings
from video_agents.production.ffmpeg import probe_size, run_ffmpeg
from video_agents.production.library import FootageLibrary, LibraryItem, count_media, jpeg_orientation
from video_agents.production.render import VideoProducer


def with_orientation(jpeg: bytes, orientation: int) -> bytes:
    """Вставляет в JPEG пометку EXIF Orientation - как делает камера телефона."""
    entry = struct.pack("<HHIHH", 0x0112, 3, 1, orientation, 0)
    tiff = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 1) + entry + struct.pack("<I", 0)
    payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    return jpeg[:2] + app1 + jpeg[2:]


def make_media(folder):
    folder.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=2", "-pix_fmt", "yuv420p", str(folder / "beach.mp4")])
    raw = folder / "raw.jpg"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=400x200", "-frames:v", "1", str(raw)])
    (folder / "trip").mkdir()
    (folder / "trip" / "pharmacy.jpg").write_bytes(with_orientation(raw.read_bytes(), 6))
    raw.unlink()
    (folder / "notes.txt").write_text("не медиа", encoding="utf-8")


def test_orientation_is_read_from_phone_photos(tmp_path):
    raw = tmp_path / "a.jpg"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=40x20", "-frames:v", "1", str(raw)])
    assert jpeg_orientation(raw) == 1
    (tmp_path / "b.jpg").write_bytes(with_orientation(raw.read_bytes(), 6))
    assert jpeg_orientation(tmp_path / "b.jpg") == 6


def test_library_studies_each_file_once_and_rotates_photos(tmp_path):
    folder = tmp_path / "my_footage"
    make_media(folder)
    assert count_media(folder) == {"videos": 1, "photos": 1}
    seen = []

    def describe(frames, kind):
        seen.append((kind, len(frames)))
        return "пляж" if kind == "video" else "аптека"

    library = FootageLibrary(folder, tmp_path / "cache", describe)
    items = {item.rel: item for item in library.scan()}
    assert set(items) == {"beach.mp4", "trip/pharmacy.jpg"}
    assert sorted(seen) == [("image", 1), ("video", 3)]
    # Фото «лёжа» 400x200 с пометкой «повернуть» становится вертикальным 200x400.
    assert probe_size(items["trip/pharmacy.jpg"].path) == (200, 400)
    assert items["beach.mp4"].path == folder / "beach.mp4"

    library.scan()
    assert len(seen) == 2  # уже изученные файлы второй раз не изучаем
    (folder / "beach.mp4").unlink()
    assert [item.rel for item in library.scan()] == ["trip/pharmacy.jpg"]


def test_own_footage_comes_first_and_continues(tmp_path, monkeypatch):
    from video_agents.production import render

    settings = Settings(workspace=str(tmp_path / "ws"))
    settings.video.width, settings.video.height, settings.video.fps = 360, 640, 15
    settings.video.music_dir = str(tmp_path / "no_music")
    folder = tmp_path / "my_footage"
    make_media(folder)
    asked = []

    def match(title, phrases, descriptions):
        asked.append((phrases, descriptions))
        return [descriptions.index("аптека"), descriptions.index("аптека")]

    library = FootageLibrary(folder, tmp_path / "cache", lambda frames, kind: "пляж" if kind == "video" else "аптека",
                             match)
    plans = []
    original = render.VideoProducer._render_scene
    monkeypatch.setattr(render.VideoProducer, "_render_scene",
                        lambda self, plan, *a: plans.append(plan) or original(self, plan, *a))

    class NoStock:
        def search(self, query):
            raise AssertionError("свои кадры подошли - стоки не нужны")

    VideoProducer(settings, FakeTTS(), NoStock(), None, None, library).produce(_two_scene_script(), tmp_path / "job")
    assert len(asked[0][0]) == 2
    assert plans[0].kind == "image" and plans[1].path == plans[0].path and plans[1].start > 0


def test_library_only_never_uses_stock(tmp_path):
    settings = Settings(workspace=str(tmp_path / "ws"))
    settings.video.width, settings.video.height, settings.video.fps = 360, 640, 15
    settings.video.music_dir = str(tmp_path / "no_music")
    settings.footage.library_only = True
    folder = tmp_path / "my_footage"
    make_media(folder)
    item = LibraryItem("beach.mp4", "video", folder / "beach.mp4", "пляж")

    class OnlySecond:
        def pick(self, title, phrases, progress=None):
            return [None, item]  # к первой фразе своего кадра нет

    class NoStock:
        def search(self, query):
            raise AssertionError("включено «только мои кадры»")

    result = VideoProducer(settings, FakeTTS(), NoStock(), None, None, OnlySecond()).produce(
        _two_scene_script(), tmp_path / "job")
    assert result.duration > 0
