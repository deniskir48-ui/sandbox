"""TikTok через Content Posting API (прямая публикация или отправка в черновики)."""

from __future__ import annotations

import json
import logging
import secrets as pysecrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from ..models import PlatformMeta, UploadResult
from .base import PublishError, Publisher, wait_until

log = logging.getLogger(__name__)

API = "https://open.tiktokapis.com"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.publish,video.upload"
CHUNK = 10 * 1024 * 1024  # TikTok принимает куски 5-64 МБ, последний может быть больше


def chunk_plan(size: int, chunk: int = CHUNK) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) по правилам TikTok: остаток уходит в последний кусок."""
    if size <= chunk:
        return size, 1
    return chunk, size // chunk


class TikTokAuth:
    def __init__(self, secrets):
        if not (secrets.tiktok_client_key and secrets.tiktok_client_secret):
            raise PublishError("Нужны TIKTOK_CLIENT_KEY и TIKTOK_CLIENT_SECRET в .env")
        self.client_key = secrets.tiktok_client_key
        self.client_secret = secrets.tiktok_client_secret
        self.redirect_uri = secrets.tiktok_redirect_uri
        self.token_file = Path(secrets.tiktok_token_file)

    def authorize_url(self) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_key": self.client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": pysecrets.token_urlsafe(16),
        })

    def exchange_code(self, code: str) -> None:
        self._token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri})

    def access_token(self) -> str:
        if not self.token_file.exists():
            raise PublishError("Нет токена TikTok. Выполните: python -m video_agents auth tiktok")
        token = json.loads(self.token_file.read_text(encoding="utf-8"))
        if token["expires_at"] - time.time() < 300:
            token = self._token_request({"grant_type": "refresh_token", "refresh_token": token["refresh_token"]})
        return token["access_token"]

    def _token_request(self, data: dict) -> dict:
        response = requests.post(
            f"{API}/v2/oauth/token/",
            data={"client_key": self.client_key, "client_secret": self.client_secret, **data},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        payload = response.json()
        if "access_token" not in payload:
            raise PublishError(f"TikTok OAuth: {payload}")
        token = {
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "expires_at": time.time() + payload["expires_in"],
            "open_id": payload.get("open_id"),
        }
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(token), encoding="utf-8")
        return token


class TikTokPublisher(Publisher):
    name = "tiktok"

    def __init__(self, config, secrets, ai_disclosure: bool):
        self.config = config
        self.auth = TikTokAuth(secrets)
        self.ai_disclosure = ai_disclosure

    def _post(self, path: str, token: str, body: dict) -> dict:
        response = requests.post(
            f"{API}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json=body,
            timeout=60,
        )
        payload = response.json()
        error = payload.get("error", {})
        if not response.ok or error.get("code") not in (None, "ok"):
            raise PublishError(f"TikTok API {path}: {error or payload}")
        return payload.get("data", {})

    def _privacy_level(self, token: str) -> str:
        info = self._post("/v2/post/publish/creator_info/query/", token, {})
        options = info.get("privacy_level_options", [])
        if self.config.privacy_level in options:
            return self.config.privacy_level
        # Непрошедшие аудит приложения TikTok могут публиковать только приватно.
        log.warning("TikTok: уровень %s недоступен (%s), публикуем как SELF_ONLY", self.config.privacy_level, options)
        return "SELF_ONLY"

    def publish(self, video_path: Path, meta: PlatformMeta) -> UploadResult:
        token = self.auth.access_token()
        size = video_path.stat().st_size
        chunk_size, total_chunks = chunk_plan(size)
        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        }
        if self.config.mode == "inbox":
            init = self._post("/v2/post/publish/inbox/video/init/", token, {"source_info": source_info})
        else:
            post_info = {
                "title": meta.tiktok_caption[:2200],
                "privacy_level": self._privacy_level(token),
                "disable_comment": self.config.disable_comment,
                "disable_duet": self.config.disable_duet,
                "disable_stitch": self.config.disable_stitch,
                "video_cover_timestamp_ms": 1000,
                "is_aigc": self.ai_disclosure,
            }
            init = self._post("/v2/post/publish/video/init/", token,
                              {"post_info": post_info, "source_info": source_info})

        self._upload(video_path, init["upload_url"], size, chunk_size, total_chunks)
        publish_id = init["publish_id"]
        final_status = {}

        def done() -> bool:
            status = self._post("/v2/post/publish/status/fetch/", token, {"publish_id": publish_id})
            if status.get("status") == "FAILED":
                raise PublishError(f"TikTok отклонил видео: {status.get('fail_reason')}")
            final_status.update(status)
            return status.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX")

        wait_until(done, timeout=900, interval=10)
        post_ids = final_status.get("publicaly_available_post_id") or []
        return UploadResult(platform=self.name, ok=True, id=str(post_ids[0]) if post_ids else publish_id)

    @staticmethod
    def _upload(video_path: Path, upload_url: str, size: int, chunk_size: int, total_chunks: int) -> None:
        with open(video_path, "rb") as fh:
            for index in range(total_chunks):
                start = index * chunk_size
                end = size - 1 if index == total_chunks - 1 else start + chunk_size - 1
                fh.seek(start)
                data = fh.read(end - start + 1)
                response = requests.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(data)),
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                    data=data,
                    timeout=600,
                )
                if response.status_code not in (200, 201, 206):
                    raise PublishError(f"TikTok upload chunk {index}: {response.status_code} {response.text[:300]}")
