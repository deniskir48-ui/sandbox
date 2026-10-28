WORDS_PER_SECOND = 2.5


def word_budget(channel) -> int:
    """Сколько слов диктора помещается в заданную длину ролика."""
    return int(channel.video_length_seconds * WORDS_PER_SECOND)


def channel_brief(channel) -> str:
    """Общая вводная о канале, которую получает каждый агент."""
    rules = "\n".join(f"- {rule}" for rule in channel.extra_rules) or "- нет"
    return (
        f"Ниша канала: {channel.niche}\n"
        f"Аудитория: {channel.audience}\n"
        f"Язык роликов: {channel.language}. ВСЕ тексты для зрителя (озвучка, надписи, заголовки, "
        f"подписи, хэштеги) пиши строго на этом языке, даже если инструкции на другом.\n"
        f"Тон: {channel.tone}\n"
        f"Длина ролика: до {channel.video_length_seconds} секунд (вертикальное видео 9:16), "
        f"это не больше {word_budget(channel)} слов текста диктора суммарно\n"
        f"Дополнительные правила канала:\n{rules}"
    )
