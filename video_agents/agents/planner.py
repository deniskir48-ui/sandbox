"""Планировщик дня: решает, о чём сегодняшний ролик, глядя на всё, что есть у автора и вокруг."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .brief import channel_brief

SYSTEM = """Ты - шеф-редактор канала коротких роликов. Раз в день ты выбираешь ОДНУ тему для сегодняшнего ролика.

Источники (используй то, что даёт самый сильный ролик именно сегодня):
- кадры автора (его видео и фото) - ролик монтируется в первую очередь из них, поэтому лучшая тема та,
  под которую у автора есть 2-3 подходящих кадра; свежие и ещё не использованные кадры - в приоритете;
- наброски автора - его собственные мысли и заготовки, очень ценный источник;
- посты автора из Threads, которые уже зашли его аудитории;
- новости и тренды - только если они реально касаются аудитории канала и проверены;
- день, погода, ветер и луна - повод, если он и правда заметный (первый дождь, хамсин, жара, праздник);
  астрологию и приметы фактами не выдавай.

Правила:
- одна узнаваемая мысль, полезная или удивительная для аудитории; не повторяй уже снятые темы;
- опирайся на материал автора, не выдумывай факты: material - это конкретика, из которой сценарист напишет текст
  (факты, советы, детали из набросков и постов, новостей), без воды;
- в media укажи номера кадров автора, которые лягут в ролик (можно пусто, если тема сильная, а кадров нет)."""


class DailyPlan(BaseModel):
    source: Literal["кадры", "набросок", "threads", "новости", "день"] = Field(
        description="Главный источник темы")
    topic: str = Field(description="Тема ролика одной фразой")
    viewer_problem: str = Field(description="Вопрос или ситуация зрителя, его словами")
    angle: str = Field(description="Чем ролик полезен или неожидан")
    hook: str = Field(description="Идея крючка: неожиданный факт для первой фразы")
    why_today: str = Field(description="Почему именно эта тема и именно сегодня, 1-2 предложения")
    material: str = Field(description="Конкретика для сценариста: факты, советы, детали - из источников, по-русски")
    media: list[int] = Field(description="Номера кадров автора для ролика (2-5) или пустой список")
    note_ids: list[str] = Field(description="id набросков, на которых построена тема, или пустой список")
    threads_post: int = Field(description="Номер поста из Threads, на котором построена тема, или 0")


class PlannerAgent:
    def __init__(self, llm, channel, web_research: bool = True):
        self.llm = llm
        self.channel = channel
        self.web_research = web_research

    def news(self) -> str:
        if not self.web_research:
            return ""
        try:
            return self.llm.research(
                system="Ты - ресёрчер. Найди свежие (за последние дни) новости, события и обсуждения, полезные "
                       "аудитории канала. Коротко, списком, с датами; только проверенное.",
                prompt=f"{channel_brief(self.channel)}\n\nЧто нового и важного для этой аудитории сейчас?",
                max_searches=3,
            )
        except Exception:
            return ""

    def plan(self, *, today: str, media: list[str], notes: list[dict], posts: list[str], past_topics: list[str],
             news: str = "") -> DailyPlan:
        def block(title: str, lines: list[str], empty: str) -> str:
            return f"{title}:\n" + ("\n".join(lines) if lines else empty)

        prompt = "\n\n".join([
            channel_brief(self.channel),
            today,
            block("Кадры автора", [f"{n}. {line}" for n, line in enumerate(media, 1)], "(папка пока пустая)"),
            block("Наброски автора", [f"[{note['id']}] {note['text'][:1500]}" for note in notes], "(нет)"),
            block("Посты автора из Threads (отобраны, ещё не сняты)",
                  [f"{n}. {text[:1500]}" for n, text in enumerate(posts, 1)], "(нет)"),
            block("Новости и тренды", [news] if news else [], "(не искали)"),
            block("Уже снятые темы (не повторять)", [f"- {t}" for t in past_topics[-60:]], "(пока ничего)"),
            "Выбери тему сегодняшнего ролика.",
        ])
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=DailyPlan, effort="medium")
