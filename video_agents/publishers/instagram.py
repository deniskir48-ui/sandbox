"""Instagram Reels через Instagram Graph API (контейнер -> загрузка файла -> публикация)."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from ..models import PlatformMeta, UploadResult
from .base import PublishError, Publisher, wait_until

log = logging.getLogger(__name__)


class InstagramPublisher(Publisher):
    name = "instagram"

    def __init__(self, config, secrets):
        if not (secrets.instagram_access_token and secrets.instagram_user_id):
            raise PublishError("Нужны INSTAGRAM_ACCESS_TOKEN и INSTAGRAM_USER_ID в .env")
        self.token = secrets.instagram_access_token
        self.user_id = secrets.instagram_user_id
        self.config = config
        self.base = f"https://{config.graph_host}/{config.api_version}"

    def _call(self, method: str, path: str, **kwargs) -> dict:
        params = kwargs.pop("params", {})
        params["access_token"] = self.token
        response = requests.request(method, f"{self.base}/{path}", params=params, timeout=60, **kwargs)
        data = response.json()
        if not response.ok or "error" in data:
            raise PublishError(f"Instagram API: {data.get('error', data)}")
        return data

    def publish(self, video_path: Path, meta: PlatformMeta) -> UploadResult:
        # 1. Контейнер для Reels с загрузкой файла напрямую (без публичного URL).
        container = self._call("POST", f"{self.user_id}/media", data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": meta.instagram_caption[:2200],
            "share_to_feed": str(self.config.share_to_feed).lower(),
        })
        container_id = container["id"]
        upload_uri = container.get("uri") or (
            f"https://rupload.facebook.com/ig-api-upload/{self.config.api_version}/{container_id}"
        )

        # 2. Загрузка файла.
        size = video_path.stat().st_size
        with open(video_path, "rb") as fh:
            response = requests.post(
                upload_uri,
                headers={"Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(size)},
                data=fh,
                timeout=600,
            )
        if not response.ok:
            raise PublishError(f"Instagram upload: {response.status_code} {response.text[:500]}")

        # 3. Ждём, пока Instagram обработает видео.
        def ready() -> bool:
            status = self._call("GET", container_id, params={"fields": "status_code,status"})
            if status.get("status_code") == "ERROR":
                raise PublishError(f"Instagram отклонил видео: {status.get('status')}")
            return status.get("status_code") == "FINISHED"

        wait_until(ready, timeout=900, interval=10)

        # 4. Публикация.
        media_id = self._call("POST", f"{self.user_id}/media_publish", data={"creation_id": container_id})["id"]
        permalink = None
        try:
            permalink = self._call("GET", media_id, params={"fields": "permalink"}).get("permalink")
        except PublishError as exc:
            log.warning("Не удалось получить ссылку на Reels: %s", exc)
        return UploadResult(platform=self.name, ok=True, id=media_id, url=permalink)
