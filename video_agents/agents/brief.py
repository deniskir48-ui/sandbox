WORDS_PER_SECOND = 2.5


def target_words(channel) -> int:
    """Сколько слов диктора в ролике обычной (целевой) длины."""
    return round(channel.video_length_seconds * WORDS_PER_SECOND)


def word_budget(channel) -> int:
    """Абсолютный максимум слов диктора: длиннее ролик быть не может."""
    return int(max(channel.max_video_length_seconds, channel.video_length_seconds) * WORDS_PER_SECOND)


def channel_brief(channel) -> str:
    """Общая вводная о канале, которую получает каждый агент."""
    rules = "\n".join(f"- {rule}" for rule in channel.extra_rules) or "- нет"
    return (
        f"Ниша канала: {channel.niche}\n"
        f"Аудитория: {channel.audience}\n"
        f"Язык роликов: {channel.language}. ВСЕ тексты для зрителя (озвучка, надписи, заголовки, "
        f"подписи, хэштеги) пиши строго на этом языке, даже если инструкции на другом.\n"
        f"Тон: {channel.tone}\n"
        f"Длина ролика (вертикальное видео 9:16): обычно около {channel.video_length_seconds} секунд "
        f"(~{target_words(channel)} слов диктора). Длиннее, до {channel.max_video_length_seconds} секунд "
        f"({word_budget(channel)} слов), - только если материал действительно сильный и каждая секунда "
        f"работает; больше нельзя\n"
        f"Дополнительные правила канала:\n{rules}"
    )
