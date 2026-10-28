"""Сборка финального вертикального ролика: озвучка + футажи + субтитры + музыка."""

from __future__ import annotations

import logging
import math
import os
import random
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ..models import Script
from .ffmpeg import detect_black_borders, probe_duration, run_ffmpeg
from .footage import Clip
from .subtitles import build_ass
from .tts import TTSProvider, Word

log = logging.getLogger(__name__)

MUSIC_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}
FONT_EXTENSIONS = {".ttf", ".otf"}
WINDOWS_FONTS = ("arial.ttf", "arialbd.ttf")
IS_WINDOWS = sys.platform == "win32"


@dataclass
class RenderResult:
    video_path: Path
    duration: float


@dataclass
class ClipPlan:
    """Какое видео ставить в сцену и с какой секунды (продолжение кадра предыдущей сцены)."""

    path: Path
    start: float = 0.0


def _first_long_enough(clips: list[Clip], duration: float) -> Clip:
    """Самый релевантный из достаточно длинных (порядок поиска = релевантность)."""
    return next((clip for clip in clips if clip.duration >= duration), clips[0])


class VideoProducer:
    def __init__(self, settings, tts: TTSProvider, footage=None, editor=None):
        self.video = settings.video
        self.subs = settings.subtitles
        self.colors = settings.footage.fallback_colors
        self.candidates = settings.footage.candidates
        self.tts = tts
        self.footage = footage
        self.editor = editor
        self._crop_cache: dict[Path, str | None] = {}

    def produce(self, script: Script, job_dir: Path) -> RenderResult:
        job_dir.mkdir(parents=True, exist_ok=True)
        fps = self.video.fps

        words: list[Word] = []
        scene_audio: list[Path] = []
        scene_video: list[Path] = []
        captions: list[tuple[float, float, str]] = []
        used_footage: set[int] = set()
        previous: ClipPlan | None = None
        cursor = 0.0

        for i, scene in enumerate(script.scenes):
            log.info("Сцена %d/%d: озвучка и видеоряд", i + 1, len(script.scenes))
            speech = self.tts.synthesize(scene.narration, job_dir / f"voice_{i:02d}.mp3")
            # Длительность сцены кратна кадру, чтобы звук и картинка не расходились.
            duration = math.ceil((speech.duration + self.video.scene_gap) * fps) / fps

            audio_path = job_dir / f"voice_{i:02d}.wav"
            run_ffmpeg(["-i", str(speech.audio_path), "-af", "apad", "-t", f"{duration:.3f}",
                        "-ar", "48000", "-ac", "2", str(audio_path)])
            scene_audio.append(audio_path)

            words.extend(Word(w.text, w.start + cursor, w.end + cursor) for w in speech.words)
            if self.subs.show_scene_text and scene.on_screen_text.strip():
                captions.append((cursor, cursor + duration, scene.on_screen_text.strip()))

            plan = self._find_clip(scene, script, duration, used_footage, previous)
            video_path = job_dir / f"scene_{i:02d}.mp4"
            self._render_scene(plan, duration, video_path, self.colors[i % len(self.colors)])
            if plan:
                previous = ClipPlan(plan.path, plan.start + duration)
            scene_video.append(video_path)
            cursor += duration

        narration = job_dir / "narration.wav"
        self._concat(scene_audio, narration, job_dir / "audio_list.txt")
        raw_video = job_dir / "video_raw.mp4"
        self._concat(scene_video, raw_video, job_dir / "video_list.txt")

        (job_dir / "subs.ass").write_text(
            build_ass(words, self.subs, self.video.width, self.video.height, captions), encoding="utf-8"
        )
        final = job_dir / "final.mp4"
        self._final_mix(job_dir, raw_video, narration, final)
        return RenderResult(final, probe_duration(final))

    def _find_clip(self, scene, script: Script, duration: float, used: set[int],
                   previous: ClipPlan | None) -> ClipPlan | None:
        """Ищет видео к сцене: запросы сцены, затем общие запросы ролика.

        Монтажёр сначала ищет точный кадр, потом - хотя бы подходящий по теме. Если подходящего нет,
        продолжаем видео предыдущей сцены: это лучше, чем случайный кадр про другое.
        """
        if not self.footage:
            return None
        queries = list(dict.fromkeys(scene.visual_queries + script.backup_queries))
        pool: list[Clip] = []
        chosen = None
        for query in queries:
            try:
                clips = [c for c in self.footage.search(query) if c.id not in used][:self.candidates]
            except Exception as exc:
                log.warning("Поиск видео '%s' не удался: %s", query, exc)
                continue
            if not clips:
                continue
            if not self.editor:
                chosen = _first_long_enough(clips, duration)
                break
            pool.extend(c for c in clips[:2] if c.id not in {p.id for p in pool})
            chosen = self._ask_editor(clips, scene.narration, script.title)
            if chosen:
                log.info("Монтажёр выбрал видео по запросу '%s'", query)
                break
            log.info("Монтажёр не нашёл подходящего видео по запросу '%s'", query)
        if not chosen and pool:
            chosen = self._ask_editor(pool[:10], scene.narration, script.title, relaxed=True)
            if chosen:
                log.info("Монтажёр взял кадр, подходящий к общей теме ролика")
        if not chosen:
            if previous:
                log.info("Подходящего видео нет - продолжаем кадр предыдущей сцены")
                return previous
            log.warning("Подходящего видео нет - будет цветной фон")
            return None
        try:
            path = self.footage.download(chosen)
        except Exception as exc:
            log.warning("Не удалось скачать видео %s: %s", chosen.id, exc)
            return previous
        used.add(chosen.id)
        return ClipPlan(path)

    def _ask_editor(self, clips: list[Clip], narration: str, title: str, relaxed: bool = False) -> Clip | None:
        with_previews = []
        for clip in clips:
            try:
                image = self.footage.preview(clip)
            except Exception as exc:
                log.debug("Нет превью для %s: %s", clip.id, exc)
                continue
            if image:
                with_previews.append((clip, image))
        if not with_previews:
            return None
        try:
            index = self.editor.choose(narration, title, [image for _, image in with_previews], relaxed=relaxed)
        except Exception as exc:
            log.warning("Монтажёр не ответил: %s", exc)
            return None
        return with_previews[index][0] if index is not None else None

    def _render_scene(self, plan: ClipPlan | None, duration: float, out: Path, color: str) -> None:
        w, h, fps = self.video.width, self.video.height, self.video.fps
        encode = ["-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                  "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
        if plan:
            # Убираем чёрные полосы исходника, заполняем кадр 9:16 и даём лёгкий наезд камеры.
            borders = self._borders(plan.path)
            vf = (f"{borders + ',' if borders else ''}"
                  f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                  f"scale=w='{w}*(1+0.04*t/{duration:.3f})':h=-2:eval=frame,crop={w}:{h},"
                  f"fps={fps},setsar=1")
            start = plan.start % max(self._duration(plan.path), 0.1)
            run_ffmpeg(["-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", str(plan.path), "-vf", vf, *encode])
        else:
            source = f"color=c={color.replace('#', '0x')}:s={w}x{h}:r={fps}:d={duration:.3f}"
            run_ffmpeg(["-f", "lavfi", "-i", source, *encode])

    def _borders(self, path: Path) -> str | None:
        if path not in self._crop_cache:
            self._crop_cache[path] = detect_black_borders(path)
        return self._crop_cache[path]

    def _duration(self, path: Path) -> float:
        try:
            return probe_duration(path)
        except Exception:
            return 0.0

    @staticmethod
    def _concat(parts: list[Path], out: Path, list_file: Path) -> None:
        list_file.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", list_file.name, "-c", "copy", out.name],
                   cwd=list_file.parent)

    def _pick_music(self) -> Path | None:
        music_dir = Path(self.video.music_dir)
        if not music_dir.is_dir():
            return None
        tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTENSIONS]
        return random.choice(tracks).resolve() if tracks else None

    def _copy_windows_fonts(self, target: Path) -> bool:
        """Копирует Arial из системной папки шрифтов Windows рядом с роликом."""
        system_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        files = [system_fonts / name for name in WINDOWS_FONTS if (system_fonts / name).exists()]
        if not files:
            return False
        target.mkdir(exist_ok=True)
        for font in files:
            shutil.copyfile(font, target / font.name)
        return True

    def _final_mix(self, job_dir: Path, video: Path, narration: Path, out: Path) -> None:
        subs_filter = "ass=subs.ass"
        fonts_dir = Path(self.video.fonts_dir)
        if fonts_dir.is_dir() and any(p.suffix.lower() in FONT_EXTENSIONS for p in fonts_dir.iterdir()):
            # Относительный путь с прямыми слэшами: «C:\...» ломает синтаксис фильтров ffmpeg на Windows.
            relative = os.path.relpath(fonts_dir.resolve(), job_dir.resolve())
            subs_filter += f":fontsdir={Path(relative).as_posix()}"
        elif IS_WINDOWS and self._copy_windows_fonts(job_dir / "fonts"):
            # Сборки ffmpeg под Windows часто не находят системные шрифты сами.
            subs_filter += ":fontsdir=fonts"

        args = ["-i", video.name, "-i", narration.name]
        music = self._pick_music()
        if music:
            args += ["-stream_loop", "-1", "-i", str(music)]
            graph = (f"[0:v]{subs_filter}[v];[2:a]volume={self.video.music_volume}[m];"
                     "[1:a][m]amix=inputs=2:duration=first:normalize=0[a]")
            audio_map = "[a]"
        else:
            graph = f"[0:v]{subs_filter}[v]"
            audio_map = "1:a"
        args += ["-filter_complex", graph, "-map", "[v]", "-map", audio_map,
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-r", str(self.video.fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                 "-movflags", "+faststart", "-shortest", out.name]
        run_ffmpeg(args, cwd=job_dir)
