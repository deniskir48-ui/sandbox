from __future__ import annotations

from .brief import channel_brief
from ..models import Review, Script, VideoIdea

SYSTEM = """Ты - строгий шеф-редактор коротких роликов. Оцениваешь сценарий так, как его
увидит зритель, листающий ленту, и как его увидит модерация платформ.

Проверь:
1. Хук: остановит ли первая фраза скролл?
2. Удержание: нет ли провисаний, повторов, воды; есть ли напряжение до конца?
3. Факты: нет ли ошибок, сомнительных утверждений, выдуманных цифр?
4. Озвучка: легко ли произносить, нет ли длинных фраз и непроизносимых символов?
5. Длина: укладывается ли текст в заданное время (~2.5 слова в секунду)?
6. Визуал: конкретны ли visual_query, найдутся ли такие кадры на стоках?
7. Риски: нарушения правил YouTube/Instagram/TikTok, авторские права, опасные советы.

approved = true только если ролик можно публиковать как есть и score >= 8."""


class CriticAgent:
    def __init__(self, llm, channel):
        self.llm = llm
        self.channel = channel

    def review(self, idea: VideoIdea, script: Script) -> Review:
        words = len(script.full_text.split())
        prompt = (
            f"{channel_brief(self.channel)}\n\n"
            f"Тема: {idea.topic}\n"
            f"Сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"В тексте диктора {words} слов (~{words / 2.5:.0f} секунд).\n"
            "Дай оценку и конкретные правки."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Review, effort="medium")
