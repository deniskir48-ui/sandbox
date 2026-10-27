def channel_brief(channel) -> str:
    """Общая вводная о канале, которую получает каждый агент."""
    rules = "\n".join(f"- {rule}" for rule in channel.extra_rules) or "- нет"
    return (
        f"Ниша канала: {channel.niche}\n"
        f"Аудитория: {channel.audience}\n"
        f"Язык роликов: {channel.language}\n"
        f"Тон: {channel.tone}\n"
        f"Длина ролика: около {channel.video_length_seconds} секунд (вертикальное видео 9:16)\n"
        f"Дополнительные правила канала:\n{rules}"
    )
