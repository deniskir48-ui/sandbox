"""Instagram Reels через Instagram Graph API (контейнер -> загрузка файла -> публикация)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from ..models import PlatformMeta, UploadResult
from .base import PublishError, Publisher, wait_until

log = logging.getLogger(__name__)


REFRESH_AFTER = 7 * 24 * 3600  # долгоживущий токен живёт 60 дней; продлеваем раз в неделю


class InstagramAuth:
    """Токен Instagram: сохраняется в файл, ID аккаунта определяется сам, токен продлевается сам."""

    def __init__(self, config, secrets):
        self.config = config
        self.secrets = secrets
        self.token_file = Path(secrets.instagram_token_file)
        self.base = f"https://{config.graph_host}/{config.api_version}"

    def is_configured(self) -> bool:
        return self.token_file.exists() or bool(self.secrets.instagram_access_token)

    def save(self, token: str) -> dict:
        """Проверяет токен и сохраняет его вместе с ID и именем аккаунта."""
        me = self._get(f"{self.base}/me", token, fields="user_id,username")
        data = {"access_token": token, "user_id": str(me["user_id"]), "username": me.get("username"),
                "saved_at": time.time()}
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(data), encoding="utf-8")
        return data

    def credentials(self) -> tuple[str, str]:
        """(токен, ID аккаунта)."""
        if self.token_file.exists():
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
        elif self.secrets.instagram_access_token and self.secrets.instagram_user_id:
            data = {"access_token": self.secrets.instagram_access_token,
                    "user_id": self.secrets.instagram_user_id, "saved_at": time.time()}
        elif self.secrets.instagram_access_token:
            data = self.save(self.secrets.instagram_access_token)
        else:
            raise PublishError("Instagram не подключён. Выполните: python -m video_agents auth instagram")
        if self.config.graph_host == "graph.instagram.com" and time.time() - data["saved_at"] > REFRESH_AFTER:
            data = self._refresh(data)
        return data["access_token"], data["user_id"]

    def _refresh(self, data: dict) -> dict:
        try:
            fresh = self._get("https://graph.instagram.com/refresh_access_token", data["access_token"],
                              grant_type="ig_refresh_token")
        except PublishError as exc:
            log.warning("Не удалось продлить токен Instagram: %s", exc)
            return data
        data = {**data, "access_token": fresh["access_token"], "saved_at": time.time()}
        self.token_file.write_text(json.dumps(data), encoding="utf-8")
        log.info("Токен Instagram продлён ещё на 60 дней")
        return data

    @staticmethod
    def _get(url: str, token: str, **params) -> dict:
        response = requests.get(url, params={**params, "access_token": token}, timeout=30)
        payload = response.json()
        if not response.ok or "error" in payload:
            raise PublishError(f"Instagram API: {payload.get('error', payload)}")
        return payload


class InstagramPublisher(Publisher):
    name = "instagram"

    def __init__(self, config, secrets):
        self.token, self.user_id = InstagramAuth(config, secrets).credentials()
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
