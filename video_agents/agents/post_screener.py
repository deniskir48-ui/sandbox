"""Отбор постов из Threads: что годится для ролика канала, а что пропустить."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .brief import channel_brief

SYSTEM = """Ты отбираешь посты автора из Threads, которые потом переделают в короткие ролики его канала.

Пропускай (use = false):
1. Посты-вопросы к подписчикам: автор спрашивает совета, мнения или рекомендации («где купить…»,
   «посоветуйте…», «выбираю…, что скажете?») и сам не даёт ни ответа, ни истории, ни вывода.
   Если вопрос - только приём, а дальше автор сам рассказывает или отвечает, пост подходит.
2. Посты не по теме канала (описание канала ниже): из них выйдет ролик, который не нужен его зрителям.

Бери (use = true): посты с мыслью, историей, фактом, советом или личным опытом по теме канала.
Отвечай по каждому посту, причину - коротко."""


class PostVerdict(BaseModel):
    post_id: str = Field(description="id поста из списка")
    use: bool = Field(description="true - из поста получится ролик для этого канала")
    reason: str = Field(description="Коротко, почему")


class Screening(BaseModel):
    verdicts: list[PostVerdict]


class PostScreenerAgent:
    def __init__(self, llm, channel):
        self.llm = llm
        self.channel = channel

    def screen(self, posts: list[dict]) -> dict[str, tuple[bool, str]]:
        """{id поста: (брать ли, причина)}."""
        listing = "\n\n".join(f"[id={post['id']}]\n{' '.join((post.get('text') or '').split())[:1500]}"
                              for post in posts)
        prompt = f"{channel_brief(self.channel)}\n\nПосты:\n\n{listing}"
        result = self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Screening, effort="low")
        return {verdict.post_id: (verdict.use, verdict.reason) for verdict in result.verdicts}
