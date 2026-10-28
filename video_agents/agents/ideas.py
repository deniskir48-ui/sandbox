from __future__ import annotations

import logging

from .brief import channel_brief
from ..models import IdeaList, VideoIdea

log = logging.getLogger(__name__)

RESEARCH_SYSTEM = """Ты - исследователь аудитории для коротких роликов (Shorts, Reels, TikTok).
Найди, что больше всего волнует аудиторию канала прямо сейчас:
- самые частые вопросы (Reddit, форумы, комментарии, «People also ask» в поиске);
- распространённые ошибки и живучие мифы;
- массовые темы, которые сейчас широко обсуждают.
Узкие новости и редкие исследования, о которых обычный человек не слышал, не нужны.
Ответь сжатым списком: вопрос или проблема словами людей + где это видно. Не выдумывай."""

IDEAS_SYSTEM = """Ты - продюсер вирусных коротких роликов. Придумываешь идеи, которые удерживают
зрителя до конца и вызывают желание досмотреть, сохранить и переслать.

Главное правило: зритель должен узнать СВОЮ проблему или вопрос в первые 2 секунды.
Проблема - массовая и знакомая; неожиданным может быть ответ, но не сама проблема.
- Хорошо: «Why you're not losing belly fat», «Stop doing crunches for abs», «What to eat before the gym».
- Плохо: узкие темы, о которых аудитория не задумывалась (конкретная добавка в сливках, редкое исследование,
  экзотический термин) - зритель не поймёт, зачем ему это, и пролистает.

Требования к идеям:
- одна идея = одна мысль и один простой конкретный совет, который можно применить сегодня;
- раскрывается за отведённое время;
- только достоверные факты, никаких медицинских/финансовых обещаний;
- не повторяй темы, которые уже были на канале;
- relatability оценивай честно: 10 - знакомо почти каждому из аудитории, 5 - половине, 2 - единицам."""


class IdeaAgent:
    def __init__(self, llm, channel, web_research: bool = True):
        self.llm = llm
        self.channel = channel
        self.web_research = web_research

    def research(self) -> str:
        if not self.web_research:
            return ""
        try:
            return self.llm.research(
                system=RESEARCH_SYSTEM,
                prompt=f"{channel_brief(self.channel)}\n\nСобери 5-10 актуальных поводов для роликов.",
            )
        except Exception as exc:  # ресёрч - необязательный шаг
            log.warning("Ресёрч трендов не удался, работаем без него: %s", exc)
            return ""

    def generate(self, count: int, past_topics: list[str]) -> list[VideoIdea]:
        research = self.research()
        past = "\n".join(f"- {topic}" for topic in past_topics[-100:]) or "- (пока ничего)"
        prompt = (
            f"{channel_brief(self.channel)}\n\n"
            f"Темы, которые уже были (не повторять):\n{past}\n\n"
            + (f"Свежие находки ресёрчера:\n{research}\n\n" if research else "")
            + f"Предложи {max(count * 3, 5)} идей и отсортируй их от самой сильной к слабой."
        )
        result = self.llm.structured(system=IDEAS_SYSTEM, prompt=prompt, output_model=IdeaList, effort="medium")
        # Узнаваемость важнее всего; при равной сохраняем порядок, который предложила модель.
        ranked = sorted(result.ideas, key=lambda idea: -idea.relatability)
        return ranked[:count]
