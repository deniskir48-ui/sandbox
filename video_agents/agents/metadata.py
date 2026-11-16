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

    def generate(self, script: Script, source_text: str = "") -> PlatformMeta:
        source = ""
        if source_text:
            source = (f"Ролик сделан по посту автора:\n«{source_text}»\n"
                      "Полезные подробности из поста, которые не вошли в ролик (расписания, часы, адреса, "
                      "ссылки, названия, пошаговые советы), коротко и по пунктам добавь в подпись Instagram и "
                      "описание YouTube - зритель найдёт их там.\n\n")
        if "описани" in script.full_text.lower() or "подпис" in script.full_text.lower():
            source += ("Ролик отправляет зрителя за подробностями в описание: ответ на это обещание обязательно "
                       "должен быть в подписи Instagram, описании YouTube и (кратко) в подписи TikTok.\n\n")
        prompt = (
            f"{channel_brief(self.channel)}\n\n"
            f"Название: {script.title}\nТекст ролика: {script.full_text}\n\n"
            f"{source}"
            "Подготовь публикационные тексты для каждой платформы."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=PlatformMeta, effort="low")
