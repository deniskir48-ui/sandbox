from __future__ import annotations

from .brief import channel_brief
from ..models import Review, Script, VideoIdea

SYSTEM = """Ты - сценарист коротких вертикальных роликов с закадровым голосом.

Правила сценария:
- первая сцена - хук, который за 2 секунды объясняет, зачем смотреть дальше;
- каждая сцена - 1-2 коротких предложения для озвучки, разговорный язык, без сложных оборотов;
- темп: новая мысль каждые 3-5 секунд, никакой воды и вступлений «привет, сегодня...»;
- примерно 2.5 слова на секунду ролика; уложись в заданную длину;
- числа пиши словами, как их произнесёт диктор; без эмодзи, хэштегов и ремарок в тексте диктора;
- visual_query - конкретная картинка для поиска на стоках, на английском (например "astronaut floating space station");
- последняя сцена завершает мысль и содержит призыв (подписаться/написать в комментариях);
- только проверенные факты."""


class ScriptwriterAgent:
    def __init__(self, llm, channel):
        self.llm = llm
        self.channel = channel

    def _brief(self, idea: VideoIdea) -> str:
        return (
            f"{channel_brief(self.channel)}\n\n"
            f"Тема: {idea.topic}\nУгол подачи: {idea.angle}\nХук: {idea.hook}"
        )

    def write(self, idea: VideoIdea) -> Script:
        prompt = f"{self._brief(idea)}\n\nНапиши сценарий ролика."
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="high")

    def revise(self, idea: VideoIdea, script: Script, review: Review) -> Script:
        problems = "\n".join(f"- {problem}" for problem in review.problems)
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Текущий сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"Редактор поставил {review.score}/10. Проблемы:\n{problems}\n\n"
            f"Указания редактора: {review.rewrite_instructions}\n\n"
            "Перепиши сценарий целиком с учётом замечаний."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="high")
