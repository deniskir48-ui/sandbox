"""Свои кадры автора: видео и фото из папки (по умолчанию assets/my_footage).

Каждый новый файл один раз «изучает» ИИ: смотрит несколько кадров и записывает, что на них видно.
При монтаже по этим описаниям к каждой фразе подбирается свой кадр - раньше стоков и картинок ИИ.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import probe_duration, run_ffmpeg

log = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
# Поворот фото с телефона (EXIF Orientation) -> фильтр ffmpeg, который ставит картинку как надо.
ORIENTATION_FILTERS = {2: "hflip", 3: "hflip,vflip", 4: "vflip", 5: "transpose=0", 6: "transpose=1",
                       7: "transpose=3", 8: "transpose=2"}


@dataclass
class LibraryItem:
    rel: str  # путь внутри папки - для описаний и подсказок
    kind: str  # video | image
    path: Path  # что монтировать: исходное видео или повёрнутая как надо копия фото
    description: str


def media_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.startswith(".")
                  and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT)


def count_media(folder: Path) -> dict[str, int]:
    files = media_files(folder)
    videos = sum(1 for p in files if p.suffix.lower() in VIDEO_EXT)
    return {"videos": videos, "photos": len(files) - videos}


def jpeg_orientation(path: Path) -> int:
    """EXIF Orientation из JPEG (1 - как есть). Телефон часто хранит фото «лёжа» с пометкой, как повернуть."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(256 * 1024)
    except OSError:
        return 1
    if data[:2] != b"\xff\xd8":
        return 1
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
            tiff = data[i + 10:i + 2 + length]
            order = "little" if tiff[:2] == b"II" else "big"
            ifd = int.from_bytes(tiff[4:8], order)
            for k in range(int.from_bytes(tiff[ifd:ifd + 2], order)):
                entry = ifd + 2 + 12 * k
                if int.from_bytes(tiff[entry:entry + 2], order) == 0x0112:
                    value = int.from_bytes(tiff[entry + 8:entry + 10], order)
                    return value if value in range(1, 9) else 1
            return 1
        if marker in (0xDA, 0xD9):  # дальше уже сама картинка
            break
        i += 2 + length
    return 1


class FootageLibrary:
    def __init__(self, folder: Path, cache_dir: Path, describe=None, match=None):
        """describe(frames, kind) -> str и match(title, phrases, descriptions) -> [индекс | None]."""
        self.folder = Path(folder)
        self.cache_dir = Path(cache_dir)
        self.describe = describe
        self.match = match
        self.index_file = self.cache_dir / "index.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, index: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.index_file)

    def scan(self, progress=lambda text: None) -> list[LibraryItem]:
        """Все файлы папки с описаниями; новые и изменённые файлы изучаются (один раз)."""
        index = self._load()
        files = media_files(self.folder)
        fresh = [p for p in files if index.get(self._rel(p), {}).get("stamp") != self._stamp(p)]
        if fresh and self.describe:
            progress(f"Изучаю ваши новые кадры: {len(fresh)}")
        for number, path in enumerate(fresh, 1):
            rel = self._rel(path)
            try:
                entry = self._study(path)
            except Exception as exc:
                hint = (" (фото HEIC: на iPhone включите Настройки - Камера - Форматы - «Наиболее совместимый»)"
                        if path.suffix.lower() in (".heic", ".heif") else "")
                log.warning("Не удалось прочитать %s: %s%s", rel, str(exc).splitlines()[0][:200], hint)
                index[rel] = {"stamp": self._stamp(path), "error": str(exc)[:300]}
                self._save(index)
                continue
            index[rel] = entry
            self._save(index)  # сохраняем после каждого файла: прерванное изучение не пропадёт
            log.info("Изучен %s (%d/%d): %s", rel, number, len(fresh), entry["description"])
        present = {self._rel(p) for p in files}
        for rel in [rel for rel in index if rel not in present]:  # файл удалили из папки
            del index[rel]
        self._save(index)
        return [LibraryItem(rel, entry["kind"], Path(entry["path"]), entry["description"])
                for rel, entry in index.items() if entry.get("description") and Path(entry["path"]).exists()]

    def pick(self, title: str, phrases: list[str], progress=lambda text: None) -> list[LibraryItem | None]:
        """Свой кадр к каждой фразе (или None, если подходящего нет)."""
        items = self.scan(progress)
        if not items or not self.match:
            return [None] * len(phrases)
        chosen = self.match(title, phrases, [item.description for item in items])
        picks = [items[i] if i is not None and 0 <= i < len(items) else None for i in chosen]
        found = sum(1 for p in picks if p)
        log.info("Ваши кадры подошли к %d из %d фраз", found, len(phrases))
        return picks

    # --- Изучение одного файла ---

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.folder).as_posix()

    @staticmethod
    def _stamp(path: Path) -> str:
        stat = path.stat()
        return f"{stat.st_size}:{int(stat.st_mtime)}"

    def _study(self, path: Path) -> dict:
        key = hashlib.sha1(self._rel(path).encode("utf-8")).hexdigest()[:12]
        thumbs_dir = self.cache_dir / "thumbs"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in VIDEO_EXT:
            kind, render_path = "video", path
            duration = probe_duration(path)
            moments = [duration * share for share in (0.1, 0.5, 0.9)] if duration > 1 else [0.0]
            frames = []
            for n, moment in enumerate(moments):
                thumb = thumbs_dir / f"{key}_{n}.jpg"
                run_ffmpeg(["-ss", f"{moment:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=512:-2", str(thumb)])
                frames.append(thumb.read_bytes())
        else:
            kind = "image"
            # Копия фото, повёрнутая как надо (телефоны часто хранят снимок «лёжа» с пометкой о повороте).
            render_path = self.cache_dir / "photos" / f"{key}.jpg"
            render_path.parent.mkdir(parents=True, exist_ok=True)
            rotate = ORIENTATION_FILTERS.get(jpeg_orientation(path))
            run_ffmpeg(["-noautorotate", "-i", str(path), "-frames:v", "1", "-q:v", "2",
                        *(["-vf", rotate] if rotate else []), str(render_path)])
            thumb = thumbs_dir / f"{key}_0.jpg"
            run_ffmpeg(["-i", str(render_path), "-vf", "scale=512:-2", str(thumb)])
            frames = [thumb.read_bytes()]
        description = self.describe(frames, kind) if self.describe else path.stem
        return {"stamp": self._stamp(path), "kind": kind, "path": str(render_path), "description": description}


def make_library(footage_config, cache_root: Path, llm=None) -> FootageLibrary | None:
    folder = Path(footage_config.library_dir)
    if not media_files(folder):
        return None
    describe = match = None
    if llm is not None:
        from ..agents.footage_editor import describe_file, match_library

        describe = lambda frames, kind: describe_file(llm, frames, kind)  # noqa: E731
        match = lambda title, phrases, descriptions: match_library(llm, title, phrases, descriptions)  # noqa: E731
    return FootageLibrary(folder, cache_root / "my_footage", describe, match)


def open_folder(folder: Path) -> Path:
    """Создаёт папку своих кадров (если её нет) и открывает её в Проводнике."""
    import os

    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(folder)  # noqa: S606
    return folder
