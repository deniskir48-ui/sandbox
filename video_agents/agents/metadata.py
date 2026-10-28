from __future__ import annotations

from .brief import channel_brief
from ..models import PlatformMeta, Script

SYSTEM = """Ты - SMM-специалист. Пишешь заголовки, описания и хэштеги под алгоритмы
YouTube Shorts, Instagram Reels и TikTok. Текст на языке канала, без лжи и
обещаний, которых нет в ролике. Хэштеги - смесь широких и нишевых."""


class MetadataAgent:
    def __init__(self, llm, channel):
        self.llm = llm
        self.channel = channel

    def generate(self, script: Script) -> PlatformMeta:
        prompt = (
            f"{channel_brief(self.channel)}\n\n"
            f"Название: {script.title}\nТекст ролика: {script.full_text}\n\n"
            "Подготовь публикационные тексты для каждой платформы."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=PlatformMeta, effort="low")
