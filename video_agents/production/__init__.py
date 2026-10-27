"""Производство ролика: озвучка, футажи, субтитры, рендер через ffmpeg."""

from .footage import make_footage
from .render import RenderResult, VideoProducer
from .tts import make_tts

__all__ = ["VideoProducer", "RenderResult", "make_tts", "make_footage"]
