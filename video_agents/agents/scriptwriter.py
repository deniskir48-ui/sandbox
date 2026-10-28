from __future__ import annotations

from .brief import channel_brief, word_budget
from ..models import Review, Script, VideoIdea

SYSTEM = """Ты - сценарист коротких вертикальных роликов с закадровым голосом.

Правила сценария:
- первая сцена - хук, который за 2 секунды объясняет, зачем смотреть дальше;
- каждая сцена - 1-2 коротких предложения для озвучки, разговорный язык, без сложных оборотов;
- темп: новая мысль каждые 3-5 секунд, никакой воды и вступлений «привет, сегодня...»;
- лимит слов из задания - жёсткий: короткий плотный ролик лучше длинного, его чаще досматривают;
- числа пиши словами, как их произнесёт диктор; без эмодзи, хэштегов и ремарок в тексте диктора;
- последняя сцена завершает мысль и содержит призыв (подписаться/написать в комментариях);
- только проверенные факты.

Правила для visual_queries (по ним ищут видео на бесплатных стоках):
- описывай то, что буквально видно в кадре: человек, действие, предмет, место
  (например "woman doing squats gym", "man jogging park morning", "fresh salad bowl vegetables");
- никаких абстракций и терминов ("metabolism", "motivation", "insulin spike") - таких видео на стоках нет;
- кадр должен прямо иллюстрировать текст сцены, а не просто тему ролика;
- первый запрос самый точный, следующие - запасные, более общие."""


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
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Напиши сценарий ролика. Текст диктора суммарно - не больше {word_budget(self.channel)} слов."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="high")

    def revise(self, idea: VideoIdea, script: Script, review: Review) -> Script:
        problems = "\n".join(f"- {problem}" for problem in review.problems)
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Текущий сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"Редактор поставил {review.score}/10. Проблемы:\n{problems}\n\n"
            f"Указания редактора: {review.rewrite_instructions}\n\n"
            f"Перепиши сценарий целиком с учётом замечаний, не больше {word_budget(self.channel)} слов диктора."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="high")

    def shorten(self, idea: VideoIdea, script: Script) -> Script:
        budget = word_budget(self.channel)
        words = len(script.full_text.split())
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"В тексте диктора {words} слов, а лимит - {budget}. Сократи до {budget} слов или меньше: "
            "убери второстепенное, сохрани хук, главный совет и призыв в конце."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="medium")
