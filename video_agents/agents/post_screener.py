"""Отбор постов из Threads: что годится для ролика канала, к какой рубрике относится, что пропустить."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .brief import channel_brief

SYSTEM = """Ты отбираешь посты автора из Threads, которые потом переделают в короткие ролики его канала.

Пропускай (use = false) посты-вопросы к подписчикам: автор спрашивает совета, мнения или рекомендации
(«где купить…», «посоветуйте…», «выбираю…, что скажете?») и сам не даёт ни ответа, ни истории, ни вывода.
Если вопрос - только приём, а дальше автор сам рассказывает или отвечает, пост подходит.
{topic_rule}
Бери (use = true): посты с мыслью, историей, фактом, советом, личным опытом, списком мест или событий.

Отдельно отметь time_sensitive = true у постов, привязанных к датам: события, праздники, афиши, акции,
расписания, «завтра будут учения…». Для них укажи relevant_until - последний день, когда пост ещё
полезен зрителю (дата последнего события; «завтра» и «на этой неделе» считай от даты публикации поста).
digest = true - если это подборка многих событий (афиша или дайджест на неделю, кинопоказы); пост про одно
событие или праздник (например, «28 октября - День Охи») - не дайджест. Устаревание по сегодняшней дате
проверяет программа - сам такие посты из-за дат не отбрасывай.
{categories_rule}
Отвечай по каждому посту, причину - коротко."""

TOPIC_RULE = "Также пропускай посты не по теме канала (описание ниже): ролик из них не нужен его зрителям.\n"


class PostVerdict(BaseModel):
    post_id: str = Field(description="id поста из списка")
    use: bool = Field(description="true - из поста получится ролик")
    category: str = Field(description="Рубрика поста - название точно как в списке рубрик; если списка нет - пустая строка")
    time_sensitive: bool = Field(description="true - пост привязан к датам (события, праздники, афиши, акции)")
    digest: bool = Field(description="true - подборка многих событий (афиша, дайджест на неделю)")
    relevant_until: str = Field(description="Для постов с датами - последний день актуальности, ГГГГ-ММ-ДД; "
                                            "для остальных пустая строка")
    reason: str = Field(description="Коротко, почему")


class Screening(BaseModel):
    verdicts: list[PostVerdict]


def category_name(rubric: str) -> str:
    """«Кипр: полезное о жизни…» -> «Кипр»."""
    return rubric.split(":", 1)[0].strip()


class PostScreenerAgent:
    def __init__(self, llm, channel, topic_filter: bool = True, exclude_topics: list[str] = (),
                 categories: list[str] = ()):
        self.llm = llm
        self.channel = channel
        self.topic_filter = topic_filter
        self.exclude_topics = list(exclude_topics)
        self.categories = list(categories)

    def screen(self, posts: list[dict]) -> dict[str, dict]:
        """{id поста: {"use", "category", "time_sensitive", "digest", "relevant_until", "reason"}}."""
        listing = "\n\n".join(
            f"[id={post['id']}, опубликован {str(post.get('timestamp', ''))[:10] or 'неизвестно'}]\n"
            f"{' '.join((post.get('text') or '').split())[:1500]}" for post in posts)
        prompt = f"{channel_brief(self.channel)}\n\nПосты:\n\n{listing}"
        rules = TOPIC_RULE if self.topic_filter else ""
        if self.exclude_topics:
            rules += ("Всегда пропускай посты на эти темы, даже если они подходят каналу: "
                      + "; ".join(self.exclude_topics) + ".\n")
        categories = ""
        if self.categories:
            categories = ("\nОтнеси каждый пост к одной рубрике (в category - только название до двоеточия):\n"
                          + "\n".join(f"- {rubric}" for rubric in self.categories) + "\n")
        system = SYSTEM.format(topic_rule=rules, categories_rule=categories)
        result = self.llm.structured(system=system, prompt=prompt, output_model=Screening, effort="low")
        return {v.post_id: {"use": v.use, "category": category_name(v.category), "time_sensitive": v.time_sensitive,
                            "digest": v.digest, "relevant_until": v.relevant_until.strip(), "reason": v.reason}
                for v in result.verdicts}
