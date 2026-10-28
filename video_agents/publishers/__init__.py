"""Агенты-публикаторы: YouTube Shorts, Instagram Reels, TikTok."""

from pathlib import Path

from .base import PublishError, Publisher
from .instagram import InstagramAuth, InstagramPublisher
from .tiktok import TikTokPublisher
from .youtube import YouTubePublisher


def is_configured(platform: str, settings) -> bool:
    """Подключена ли площадка (есть ли сохранённый доступ)."""
    secrets = settings.secrets
    if platform == "youtube":
        return Path(secrets.youtube_token_file).exists()
    if platform == "instagram":
        return InstagramAuth(settings.publish.instagram, secrets).is_configured()
    if platform == "tiktok":
        return Path(secrets.tiktok_token_file).exists()
    return False


def make_publisher(platform: str, settings) -> Publisher:
    publish = settings.publish
    if platform == "youtube":
        return YouTubePublisher(publish.youtube, settings.secrets, settings.channel.language, publish.ai_disclosure)
    if platform == "instagram":
        return InstagramPublisher(publish.instagram, settings.secrets)
    if platform == "tiktok":
        return TikTokPublisher(publish.tiktok, settings.secrets, publish.ai_disclosure)
    raise ValueError(f"Неизвестная платформа: {platform}")


__all__ = ["Publisher", "PublishError", "make_publisher", "is_configured", "YouTubePublisher", "InstagramPublisher", "TikTokPublisher"]
