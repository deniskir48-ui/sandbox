"""Настройки системы: config.yaml (что снимаем) + .env (ключи и токены)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ChannelConfig(BaseModel):
    niche: str = "Удивительные факты о космосе"
    audience: str = "Люди 18-35 лет, которые листают ленту и любят узнавать новое"
    language: str = "ru"
    tone: str = "Живой, разговорный, с интригой; без канцелярита и воды"
    video_length_seconds: int = 45
    extra_rules: list[str] = Field(default_factory=list)
    # Добавляется в конец описания YouTube и подписи Instagram (например, «not medical advice»).
    disclaimer: str = ""


class LLMConfig(BaseModel):
    model: str = "claude-opus-5-5"
    web_research: bool = True
    max_revisions: int = 2
    min_score: int = 8


class VoiceConfig(BaseModel):
    provider: Literal["edge", "elevenlabs"] = "edge"
    voice: str = "ru-RU-SvetlanaNeural"
    rate: str = "+8%"
    elevenlabs_model: str = "eleven_multilingual_v2"


class FootageConfig(BaseModel):
    provider: Literal["pexels", "none"] = "pexels"
    fallback_colors: list[str] = Field(default_factory=lambda: ["#0f2027", "#203a43", "#2c5364"])


class SubtitleConfig(BaseModel):
    font: str = "Arial"
    font_size: int = 86
    color: str = "#FFFFFF"
    highlight_color: str = "#FFD700"
    outline_color: str = "#000000"
    outline: int = 6
    max_words: int = 3
    uppercase: bool = True
    margin_v: int = 700


class VideoConfig(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    scene_gap: float = 0.15
    music_dir: str = "assets/music"
    music_volume: float = 0.12
    fonts_dir: str = "assets/fonts"


class YouTubeConfig(BaseModel):
    privacy: Literal["public", "unlisted", "private"] = "private"
    category_id: str = "27"  # Education
    made_for_kids: bool = False


class InstagramConfig(BaseModel):
    graph_host: str = "graph.instagram.com"
    api_version: str = "v23.0"
    share_to_feed: bool = True


class TikTokConfig(BaseModel):
    mode: Literal["direct", "inbox"] = "direct"
    privacy_level: str = "SELF_ONLY"
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False


class PublishConfig(BaseModel):
    auto_publish: bool = False
    platforms: list[Literal["youtube", "instagram", "tiktok"]] = Field(
        default_factory=lambda: ["youtube", "instagram", "tiktok"]
    )
    ai_disclosure: bool = True
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    instagram: InstagramConfig = Field(default_factory=InstagramConfig)
    tiktok: TikTokConfig = Field(default_factory=TikTokConfig)


class Secrets(BaseModel):
    pexels_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    youtube_client_secrets: str = "secrets/youtube_client_secret.json"
    youtube_token_file: str = "secrets/youtube_token.json"
    instagram_access_token: str | None = None
    instagram_user_id: str | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    tiktok_redirect_uri: str | None = None
    tiktok_token_file: str = "secrets/tiktok_token.json"

    @classmethod
    def from_env(cls) -> "Secrets":
        values = {}
        for name in cls.model_fields:
            env_value = os.getenv(name.upper())
            if env_value:
                values[name] = env_value
        return cls(**values)


class Settings(BaseModel):
    channel: ChannelConfig = Field(default_factory=ChannelConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    footage: FootageConfig = Field(default_factory=FootageConfig)
    subtitles: SubtitleConfig = Field(default_factory=SubtitleConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    workspace: str = "workspace"
    secrets: Secrets = Field(default_factory=Secrets, exclude=True)


def load_settings(path: str | Path | None = "config.yaml") -> Settings:
    load_dotenv()
    data = {}
    if path and Path(path).exists():
        data = YAML(typ="safe").load(Path(path).read_text(encoding="utf-8")) or {}
    settings = Settings(**data)
    settings.secrets = Secrets.from_env()
    return settings
