from __future__ import annotations

from .brief import channel_brief, target_words, word_budget
from ..models import Review, Scene, Script, VideoIdea

SYSTEM = """Ты - сценарист коротких вертикальных роликов с закадровым голосом.

Правила сценария:
- первая сцена - хук: называет знакомую проблему зрителя его словами, чтобы он узнал себя за 2 секунды;
- каждая сцена - одна короткая фраза на 2-3 секунды, разговорный язык, без сложных оборотов;
- никакой воды и вступлений «привет, сегодня...»: ролики очень короткие, сразу к сути;
- короче - лучше: короткий ролик чаще досматривают и пересматривают, а это главный сигнал для алгоритмов;
  выходи за обычную длину, только если без этого теряется по-настоящему сильная мысль;
- числа пиши словами, как их произнесёт диктор; без эмодзи, хэштегов и ремарок в тексте диктора;
- зритель должен уйти с пользой: если ролик называет проблему, он обязательно говорит, что с ней делать;
- в озвучке не перечисляй подробности (расписания по дням, часы, адреса, цены по пунктам): обобщи одной фразой
  («по средам и субботам - только до обеда»), подробности уйдут в подпись к ролику;
- последняя сцена завершает мысль; призыв - максимум 3-4 слова (например "Follow for more") и только
  если на него есть время; вопрос зрителю лучше оставить для подписи к ролику;
- только проверенные факты.

Правила для visual_queries (по ним ищут видео на бесплатных стоках):
- описывай то, что буквально видно в кадре: человек, действие, предмет, место
  (например "woman doing squats gym", "man jogging park morning", "fresh salad bowl vegetables");
- никаких абстракций и терминов ("metabolism", "motivation", "insulin spike") - таких видео на стоках нет;
- кадр должен прямо иллюстрировать текст сцены, а не просто тему ролика;
- первый запрос самый точный, следующие - запасные, более общие;
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
                "Сохрани голос автора: его мысль, факты, формулировки и юмор. Если пост длинный - выбери "
                "главную мысль и самый сильный момент, остальное убери; если короткий - не раздувай. "
                "Если в посте есть решение, лайфхак или вывод (что делать, куда идти, как обойти проблему) - "
                "это главное в ролике: схема «проблема - решение», решение обязательно и получает больше "
                "времени, чем описание проблемы. Подробные расписания, списки часов и адресов не зачитывай - "
                "одна обобщающая фраза. "
                "Если это афиша или дайджест событий - оставь 3-5 самых интересных, даты и места коротко; "
                "если список советов или мест - 2-3 самых полезных. "
                "Хук - самая цепляющая фраза поста, переписанная для речи."
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
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="high")

    def revise(self, idea: VideoIdea, script: Script, review: Review) -> Script:
        problems = "\n".join(f"- {problem}" for problem in review.problems)
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Текущий сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"Редактор поставил {review.score}/10. Проблемы:\n{problems}\n\n"
            f"Указания редактора: {review.rewrite_instructions}\n\n"
            f"Перепиши сценарий целиком с учётом замечаний. {self._length()}"
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="high")

    def shorten(self, idea: VideoIdea, script: Script) -> Script:
        budget = word_budget(self.channel)
        words = len(script.full_text.split())
        prompt = (
            f"{self._brief(idea)}\n\n"
            f"Сценарий (JSON):\n{script.model_dump_json(indent=2)}\n\n"
            f"В тексте диктора {words} слов, а максимум - {budget}. Сократи, лучше всего до "
            f"~{target_words(self.channel)} слов: убери второстепенное и подробности, сохрани хук и решение/главный совет."
        )
        return self.llm.structured(system=SYSTEM, prompt=prompt, output_model=Script, effort="medium")

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
