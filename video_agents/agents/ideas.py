from __future__ import annotations

import logging

from .brief import channel_brief
from ..models import IdeaList, VideoIdea

log = logging.getLogger(__name__)

RESEARCH_SYSTEM = """Ты - исследователь трендов для короткого вертикального видео (Shorts, Reels, TikTok).
Найди свежие поводы, новости, вопросы и споры по нише канала, которые сейчас обсуждают.
Ответь сжатым списком находок с датами и источниками. Не выдумывай факты."""

IDEAS_SYSTEM = """Ты - продюсер вирусных коротких роликов. Придумываешь идеи, которые удерживают
зрителя до конца и вызывают желание досмотреть, сохранить и переслать.

Требования к идеям:
- одна идея = одна мысль, которую можно раскрыть за отведённое время;
- сильный хук в первой фразе: парадокс, вопрос, неожиданная цифра, конфликт;
- только достоверные факты, никаких медицинских/финансовых обещаний;
- не повторяй темы, которые уже были на канале."""


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
        return result.ideas[:count]
