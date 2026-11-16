"""Аналитик формата: по постам автора в Threads предлагает, о чём и как снимать ролики."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..threads import describe, score

SYSTEM = """Ты - продюсер коротких вертикальных роликов (Instagram Reels). Автор хочет перевести свой
Instagram на темы, которые он ведёт в Threads, где у него уже есть живая аудитория.

Изучи его посты со статистикой и найди, что именно заходит: темы, подача, личный опыт, интонация.
Предложи формат канала коротких роликов, который опирается на сильные стороны автора.

Учитывай, как делаются ролики: голос диктора (синтез речи) + субтитры + стоковые видео. Снимать себя автор
не будет, кадры из фильмов и игр показывать нельзя (авторские права) - формат должен работать на голосе
и тексте, а видеоряд - иллюстрация. Кипр на стоках есть (пляжи, города, природа, улицы).

Пиши всё по-русски, конкретно, без воды. Правила канала - короткие и проверяемые."""


class ChannelProposal(BaseModel):
    niche: str = Field(description="О чём канал: 1-2 предложения, конкретно")
    audience: str = Field(description="Для кого: кто эти люди, что их волнует")
    tone: str = Field(description="Тон и подача: как говорит автор, что делает его узнаваемым")
    video_length_seconds: int = Field(description="Обычная длина ролика в секундах (обычно 15-30)")
    max_video_length_seconds: int = Field(description="Потолок длины для сильных роликов, секунды (до 45)")
    extra_rules: list[str] = Field(description="4-8 правил для сценаристов: что делать и чего избегать")
    disclaimer: str = Field(description="Дисклеймер в описание ролика или пустая строка, если не нужен")
    example_topics: list[str] = Field(description="5 конкретных тем первых роликов на основе лучших постов")
    reasoning: str = Field(description="Почему такой формат: какие посты и темы заходят лучше всего, 2-4 предложения")


class ChannelAdvisorAgent:
    def __init__(self, llm):
        self.llm = llm

    def propose(self, posts: list[dict], hint: str = "", language: str = "ru",
                all_topics: bool = False) -> ChannelProposal:
        """all_topics - канал-блог со всеми темами автора: ничего не исключать, правила - по типам постов."""
        best = sorted((p for p in posts if p.get("text")), key=score, reverse=True)[:30]
        recent = [p for p in posts if p.get("text")][:20]  # выгрузка идёт от новых к старым
        prompt = (
            f"Язык роликов: {language}.\n"
            + (f"Автор так описывает, о чём пишет: {hint}\n" if hint else "")
            + f"\nВсего постов в Threads: {len(posts)}.\n\nЛучшие посты по просмотрам и реакциям:\n"
            + "\n".join(f"- {describe(p)}" for p in best)
            + "\n\nПоследние посты:\n"
            + "\n".join(f"- {describe(p)}" for p in recent)
            + "\n\nПредложи формат канала коротких роликов."
            + ("\n\nВажно: ролики будут переделками ВСЕХ постов автора, кроме вопросов без ответа. Поэтому "
               "канал - это его личный блог: в niche перечисли все его темы, ничего не исключай (даже если "
               "какая-то тема слабее по цифрам). Правила напиши по типам постов: личный опыт и советы, "
               "истории, разборы слов или фактов, списки мест, афиши и дайджесты событий (сжимать до 3-5 "
               "событий с датами) - чтобы сценарист знал, как адаптировать каждый тип. Правил, которые "
               "подходят только одному типу, не делай общими." if all_topics else "")
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=ChannelProposal, effort="high")


def proposal_text(proposal: ChannelProposal) -> str:
    rules = "\n".join(f"  - {rule}" for rule in proposal.extra_rules)
    topics = "\n".join(f"  {n}. {topic}" for n, topic in enumerate(proposal.example_topics, 1))
    return (
        f"О чём: {proposal.niche}\n\n"
        f"Для кого: {proposal.audience}\n\n"
        f"Подача: {proposal.tone}\n\n"
        f"Длина: обычно {proposal.video_length_seconds} с, сильные ролики - до {proposal.max_video_length_seconds} с\n\n"
        f"Правила:\n{rules}\n\n"
        + (f"Дисклеймер: {proposal.disclaimer}\n\n" if proposal.disclaimer.strip() else "")
        + f"Первые темы:\n{topics}\n\n"
        f"Почему так: {proposal.reasoning}"
    )
