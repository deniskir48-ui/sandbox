"""Смена формата канала: записать предложение аналитика в config.yaml и подготовить очередь тем."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from .agents.channel_advisor import ChannelProposal
from .models import manual_idea

VOICES = {
    "male": ("мужской", "ru-RU-DmitryNeural"),
    "female": ("женский", "ru-RU-SvetlanaNeural"),
}


def write_config(path: Path, proposal: ChannelProposal, language: str, voice: str,
                 topic_filter: bool | None = None) -> None:
    """Меняет в config.yaml только канал и голос; комментарии и остальные настройки сохраняются."""
    yaml = YAML()  # режим round-trip: сохраняет комментарии и порядок ключей
    data = yaml.load(path.read_text(encoding="utf-8")) if path.exists() else None
    if data is None:
        data = {}
    channel = data.setdefault("channel", {})
    channel["niche"] = proposal.niche
    channel["audience"] = proposal.audience
    channel["language"] = language
    channel["tone"] = proposal.tone
    channel["video_length_seconds"] = proposal.video_length_seconds
    channel["max_video_length_seconds"] = max(proposal.max_video_length_seconds, proposal.video_length_seconds)
    channel["extra_rules"] = list(proposal.extra_rules)
    channel["disclaimer"] = proposal.disclaimer.strip()
    voice_section = data.setdefault("voice", {})
    voice_section["provider"] = "edge"
    voice_section["voice"] = voice
    if topic_filter is not None:
        data.setdefault("threads", {})["topic_filter"] = topic_filter
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh)


def apply_proposal(pipeline, config_path: Path, proposal: ChannelProposal, language: str, voice: str,
                   topic_filter: bool | None = None, queue_examples: bool = True) -> int:
    """Применяет формат сразу (без перезапуска). queue_examples - заменить очередь на предложенные темы;
    возвращает, сколько старых тем убрано (они сохраняются в ideas_queue.backup.json)."""
    write_config(config_path, proposal, language, voice, topic_filter)
    if topic_filter is not None:
        pipeline.settings.threads.topic_filter = topic_filter

    channel = pipeline.settings.channel  # агенты держат ссылку на этот объект - меняем его на месте
    channel.niche = proposal.niche
    channel.audience = proposal.audience
    channel.language = language
    channel.tone = proposal.tone
    channel.video_length_seconds = proposal.video_length_seconds
    channel.max_video_length_seconds = max(proposal.max_video_length_seconds, proposal.video_length_seconds)
    channel.extra_rules = list(proposal.extra_rules)
    channel.disclaimer = proposal.disclaimer.strip()
    pipeline.settings.voice.provider = "edge"
    pipeline.settings.voice.voice = voice
    pipeline._producer = None  # пересоздастся с новым голосом
    if not queue_examples:  # ролики пойдут из постов - очередь не трогаем
        return 0

    store = pipeline.store
    with store.lock:
        old = store.queue()
        if old:
            backup = store.root / "ideas_queue.backup.json"
            backup.write_text(store.queue_file.read_text(encoding="utf-8"), encoding="utf-8")
        store.save_queue([manual_idea(topic) for topic in proposal.example_topics])
    return len(old)
