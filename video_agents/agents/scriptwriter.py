from __future__ import annotations

from .brief import channel_brief, target_words, word_budget
from ..models import ArcScript, Review, Scene, Script, VideoIdea

SYSTEM = """Ты - сценарист коротких вертикальных роликов с закадровым голосом.

Драматургия ролика (каркас по умолчанию; логику сохраняй, формулировки - свои):
1. Хук - неожиданный факт, на который хочется сказать «да ладно?». Не тема ролика, а крючок.
2. Усиление - короткая добивка, от которой становится ещё хуже или удивительнее (2-4 слова).
3. Проблема - живая ситуация зрителя, в которой этот факт бьёт по нему; лучше вопросом.
4. Решение - одно, коротко и конкретно: что делать.
5. Финал - куда за подробностями («Как найти - читайте в описании») или короткий вывод.
Образец (пост про аптеки на Кипре - расписание, дежурные аптеки, где их искать):
   «На Кипре у аптек тоже есть обед.» / «И выходные.» / «Что делать, если сразу после обеда скрутило живот?» /
   «Искать ближайшую дежурную аптеку.» / «Как её найти - читайте в описании.»
Это не шаблон для копирования: если материал не про проблему (обзор, слово дня, история) - строй
аналогично: крючок, усиление, суть, финал.

Правила сценария:
- каждая сцена - ОДНА короткая фраза, лучше 3-8 слов, максимум 10; сцена - это кадр, длинный кадр
  зритель пролистывает; длиннее мысль - разбей на две сцены;
- один ролик - одна мысль и одно решение; подробности (расписания, адреса, сайты, список шагов)
  в озвучку не попадают - они в описании ролика, а финал на него ссылается;
- никакой воды и вступлений «привет, сегодня...»: сразу к сути;
- короче - лучше: короткий ролик чаще досматривают и пересматривают, а это главный сигнал для алгоритмов;
  выходи за обычную длину, только если без этого теряется по-настоящему сильная мысль;
- числа пиши словами, как их произнесёт диктор; без эмодзи, хэштегов и ремарок в тексте диктора;
- зритель должен уйти с пользой: если ролик называет проблему, он обязательно говорит, что с ней делать;
- вопрос зрителю для комментариев лучше оставить для подписи к ролику;
- только проверенные факты.

Правила для visual_queries (по ним ищут видео на бесплатных стоках):
- описывай то, что буквально видно в кадре: человек, действие, предмет, место
  (например "woman doing squats gym", "man jogging park morning", "fresh salad bowl vegetables");
- никаких абстракций и терминов ("metabolism", "motivation", "insulin spike") - таких видео на стоках нет;
- кадр должен прямо иллюстрировать текст сцены, а не просто тему ролика;
- первый запрос самый точный, следующие - запасные, более общие;
- image_prompt - запасная картинка ИИ к сцене, если на стоках ничего нет: сцена БЕЗ людей, только предметы
  и места, без надписей, на английском (к «скрутило живот» - "blister of pills and a glass of water on a
  kitchen table, evening");
- backup_queries - 2-3 общих сюжета по теме всего ролика (например "woman drinking coffee kitchen"),
  на случай если для какой-то сцены точного кадра не найдётся."""


class ScriptwriterAgent:
    def __init__(self, llm, channel):
        self.llm = llm
        self.channel = channel

    def _brief(self, idea: VideoIdea) -> str:
        if idea.source_text:
            return (
                f"{channel_brief(self.channel)}\n\n"
                f"Ролик - адаптация поста автора из Threads, который уже зашёл аудитории "
                f"({idea.why_it_works}). Пост:\n«{idea.source_text}»\n\n"
                "Сохрани голос автора: его факты, юмор и словечки, но построй ролик по каркасу драматургии. "
                "Из поста возьми один самый неожиданный факт для хука и одно главное решение; всё остальное "
                "(расписания, сайты, списки, оговорки, побочные темы) пойдёт в описание ролика. "
                "Если в посте есть решение или лайфхак - оно обязательно в ролике. "
                "Если это афиша или дайджест событий - оставь 3-5 самых интересных, даты и места коротко. "
                "Хук - самый удивительный факт поста, переписанный для речи."
            )
        return (
            f"{channel_brief(self.channel)}\n\n"
            f"Проблема зрителя: {idea.viewer_problem}\n"
            f"Тема: {idea.topic}\nУгол подачи: {idea.angle}\nХук: {idea.hook}"
        )

    def _length(self) -> str:
        return (f"Текст диктора суммарно - около {target_words(self.channel)} слов, "
                f"абсолютный максимум {word_budget(self.channel)}.")

    def write(self, idea: VideoIdea) -> Script:
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Напиши сценарий ролика. {self._length()}"
        )
        return self._arc(prompt, "high")

    def revise(self, idea: VideoIdea, script: Script, review: Review) -> Script:
        problems = "\n".join(f"- {problem}" for problem in review.problems)
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Текущий сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"Редактор поставил {review.score}/10. Проблемы:\n{problems}\n\n"
            f"Указания редактора: {review.rewrite_instructions}\n\n"
            f"Перепиши сценарий целиком с учётом замечаний. {self._length()}"
        )
        return self._arc(prompt, "high")

    def shorten(self, idea: VideoIdea, script: Script) -> Script:
        budget = word_budget(self.channel)
        words = len(script.full_text.split())
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"В тексте диктора {words} слов, а максимум - {budget}. Сократи, лучше всего до "
            f"~{target_words(self.channel)} слов: убери второстепенное и подробности, сохрани хук и решение/главный совет."
        )
        return self._arc(prompt, "medium")

    def _arc(self, prompt: str, effort: str) -> Script:
        """Сценарий раскладывается по ячейкам каркаса; лишние сцены в ячейках отбрасываются."""
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=ArcScript, effort=effort).to_script()

    def restage(self, idea: VideoIdea, script: Script, lines: list[str], llm=None) -> Script:
        """Автор поправил текст руками и изменил число фраз: подбираем к фразам кадры, текст не трогаем."""
        numbered = "\n".join(f"{n}. {line}" for n, line in enumerate(lines, 1))
        prompt = (
            f"{channel_brief(self.channel)}\n\n"
            f"Автор сам написал текст диктора, по фразе на сцену:\n{numbered}\n\n"
            f"Сделай сценарий ровно из {len(lines)} сцен: narration каждой сцены - соответствующая фраза БЕЗ "
            "изменений, к ней подбери visual_queries и on_screen_text. Название и backup_queries - по смыслу текста."
        )
        fresh = (llm or self.llm).structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="low")
        scenes = []
        for index, line in enumerate(lines):
            # Текст автора - закон: даже если модель что-то поменяла или ошиблась с числом сцен.
            source = fresh.scenes[index] if index < len(fresh.scenes) else (
                fresh.scenes[-1] if fresh.scenes else script.scenes[min(index, len(script.scenes) - 1)])
            scenes.append(Scene(narration=line, visual_queries=source.visual_queries,
                                on_screen_text=source.on_screen_text))
        return Script(title=script.title, scenes=scenes, call_to_action=script.call_to_action,
                      backup_queries=fresh.backup_queries or script.backup_queries)
