"""Сборка финального вертикального ролика: озвучка + футажи + субтитры + музыка."""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from pathlib import Path

from ..models import Script
from .ffmpeg import probe_duration, run_ffmpeg
from .subtitles import build_ass
from .tts import TTSProvider, Word

log = logging.getLogger(__name__)

MUSIC_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}


@dataclass
class RenderResult:
    video_path: Path
    duration: float


class VideoProducer:
    def __init__(self, settings, tts: TTSProvider, footage=None):
        self.video = settings.video
        self.subs = settings.subtitles
        self.colors = settings.footage.fallback_colors
        self.tts = tts
        self.footage = footage

    def produce(self, script: Script, job_dir: Path) -> RenderResult:
        job_dir.mkdir(parents=True, exist_ok=True)
        fps = self.video.fps

        words: list[Word] = []
        scene_audio: list[Path] = []
        scene_video: list[Path] = []
        captions: list[tuple[float, float, str]] = []
        used_footage: set[int] = set()
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
            if scene.on_screen_text.strip():
                captions.append((cursor, cursor + duration, scene.on_screen_text.strip()))

            clip = self._find_clip(scene.visual_query, duration, used_footage)
            video_path = job_dir / f"scene_{i:02d}.mp4"
            self._render_scene(clip, duration, video_path, self.colors[i % len(self.colors)])
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

    def _find_clip(self, query: str, duration: float, used: set[int]) -> Path | None:
        if not self.footage:
            return None
        try:
            found = self.footage.find(query, duration, used)
        except Exception as exc:
            log.warning("Не удалось найти футаж '%s': %s", query, exc)
            return None
        if not found:
            log.warning("Футаж по запросу '%s' не найден - будет фон", query)
            return None
        video_id, path = found
        used.add(video_id)
        return path

    def _render_scene(self, clip: Path | None, duration: float, out: Path, color: str) -> None:
        w, h, fps = self.video.width, self.video.height, self.video.fps
        encode = ["-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                  "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
        if clip:
            # Заполняем кадр 9:16 с обрезкой лишнего и лёгким наездом камеры.
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                  f"scale=w='{w}*(1+0.04*t/{duration:.3f})':h=-2:eval=frame,crop={w}:{h},"
                  f"fps={fps},setsar=1")
            run_ffmpeg(["-stream_loop", "-1", "-i", str(clip), "-vf", vf, *encode])
        else:
            source = f"color=c={color.replace('#', '0x')}:s={w}x{h}:r={fps}:d={duration:.3f}"
            run_ffmpeg(["-f", "lavfi", "-i", source, *encode])

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

    def _final_mix(self, job_dir: Path, video: Path, narration: Path, out: Path) -> None:
        subs_filter = "ass=subs.ass"
        fonts_dir = Path(self.video.fonts_dir)
        if fonts_dir.is_dir() and any(fonts_dir.iterdir()):
            subs_filter += f":fontsdir={fonts_dir.resolve()}"

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
