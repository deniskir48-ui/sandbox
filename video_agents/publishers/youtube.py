"""YouTube Shorts через YouTube Data API v3 (OAuth, загрузка с докачкой)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import PlatformMeta, UploadResult
from .base import PublishError, Publisher

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def authorize(client_secrets: str, token_file: str) -> None:
    """Однократная авторизация в браузере; токен сохраняется и дальше обновляется сам."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    Path(token_file).parent.mkdir(parents=True, exist_ok=True)
    Path(token_file).write_text(credentials.to_json(), encoding="utf-8")


def load_credentials(token_file: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not Path(token_file).exists():
        raise PublishError(f"Нет токена YouTube ({token_file}). Выполните: python -m video_agents auth youtube")
    credentials = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not credentials.valid:
        credentials.refresh(Request())
        Path(token_file).write_text(credentials.to_json(), encoding="utf-8")
    return credentials


class YouTubePublisher(Publisher):
    name = "youtube"

    def __init__(self, config, secrets, language: str, ai_disclosure: bool):
        self.config = config
        self.token_file = secrets.youtube_token_file
        self.language = language
        self.ai_disclosure = ai_disclosure

    def publish(self, video_path: Path, meta: PlatformMeta) -> UploadResult:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        youtube = build("youtube", "v3", credentials=load_credentials(self.token_file), cache_discovery=False)
        description = meta.youtube_description
        if "#shorts" not in description.lower():
            description += "\n\n#shorts"
        body = {
            "snippet": {
                "title": meta.youtube_title[:100],
                "description": description[:5000],
                "tags": meta.youtube_tags[:30],
                "categoryId": self.config.category_id,
                "defaultLanguage": self.language,
                "defaultAudioLanguage": self.language,
            },
            "status": {
                "privacyStatus": self.config.privacy,
                "selfDeclaredMadeForKids": self.config.made_for_kids,
                "containsSyntheticMedia": self.ai_disclosure,
            },
        }
        media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log.info("YouTube: загружено %d%%", int(status.progress() * 100))
        video_id = response["id"]
        return UploadResult(platform=self.name, ok=True, id=video_id, url=f"https://youtube.com/shorts/{video_id}")
