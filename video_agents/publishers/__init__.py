"""Агенты-публикаторы: YouTube Shorts, Instagram Reels, TikTok."""

from .base import PublishError, Publisher
from .instagram import InstagramPublisher
from .tiktok import TikTokPublisher
from .youtube import YouTubePublisher


def make_publisher(platform: str, settings) -> Publisher:
    publish = settings.publish
    if platform == "youtube":
        return YouTubePublisher(publish.youtube, settings.secrets, settings.channel.language, publish.ai_disclosure)
    if platform == "instagram":
        return InstagramPublisher(publish.instagram, settings.secrets)
    if platform == "tiktok":
        return TikTokPublisher(publish.tiktok, settings.secrets, publish.ai_disclosure)
    raise ValueError(f"Неизвестная платформа: {platform}")


__all__ = ["Publisher", "PublishError", "make_publisher", "YouTubePublisher", "InstagramPublisher", "TikTokPublisher"]
