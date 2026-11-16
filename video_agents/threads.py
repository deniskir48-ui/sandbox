"""Выгрузка своих постов из Threads со статистикой (Threads API).

Посты и их метрики сохраняются в workspace/threads_posts.json и в таблицу threads_posts.csv (открывается
в Excel), а лучшие по просмотрам получает агент идей - как подсказку, что заходит аудитории.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API = "https://graph.threads.com/v1.0"
REFRESH_URL = "https://graph.threads.com/refresh_access_token"
REFRESH_AFTER = 7 * 24 * 3600  # ключ живёт 60 дней; продлевать можно не раньше чем через сутки
METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
BASIC_METRICS = ["likes", "replies", "reposts", "quotes"]  # views и shares Meta помечает как «в разработке»
POST_FIELDS = "id,media_type,text,permalink,timestamp"
CACHE_HOURS = 24


class ThreadsError(RuntimeError):
    pass


def _get(url: str, token: str, **params) -> dict:
    response = requests.get(url, params={**params, "access_token": token}, timeout=30)
    try:
        payload = response.json()
    except ValueError:
        raise ThreadsError(f"Threads API: HTTP {response.status_code}") from None
    if not response.ok or "error" in payload:
        error = payload.get("error", {})
        raise ThreadsError(f"Threads API: {error.get('message', payload)}")
    return payload


class ThreadsAuth:
    def __init__(self, secrets):
        self.token_file = Path(secrets.threads_token_file)

    def is_configured(self) -> bool:
        return self.token_file.exists()

    def save(self, token: str) -> dict:
        """Проверяет ключ и сохраняет его вместе с именем аккаунта."""
        me = _get(f"{API}/me", token.strip(), fields="id,username")
        data = {"access_token": token.strip(), "user_id": me["id"], "username": me.get("username"),
                "saved_at": time.time()}
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(data), encoding="utf-8")
        return data

    def token(self) -> str:
        if not self.token_file.exists():
            raise ThreadsError("Threads не подключён: python -m video_agents auth threads (или /threads <ключ> в боте)")
        data = json.loads(self.token_file.read_text(encoding="utf-8"))
        if time.time() - data["saved_at"] > REFRESH_AFTER:
            try:
                fresh = _get(REFRESH_URL, data["access_token"], grant_type="th_refresh_token")
                data = {**data, "access_token": fresh["access_token"], "saved_at": time.time()}
                self.token_file.write_text(json.dumps(data), encoding="utf-8")
                log.info("Ключ Threads продлён ещё на 60 дней")
            except ThreadsError as exc:
                log.warning("Не удалось продлить ключ Threads: %s", exc)
        return data["access_token"]


def _insights(media_id: str, token: str) -> dict[str, int]:
    """Метрики поста; если «расширенные» метрики недоступны, берём базовые."""
    for metrics in (METRICS, BASIC_METRICS):
        try:
            payload = _get(f"{API}/{media_id}/insights", token, metric=",".join(metrics))
        except ThreadsError as exc:
            log.debug("Метрики %s для %s недоступны: %s", metrics, media_id, exc)
            continue
        result = {}
        for item in payload.get("data", []):
            values = item.get("values") or [{}]
            result[item["name"]] = int(values[0].get("value") or 0)
        return result
    return {}


def fetch_posts(token: str, max_posts: int = 200) -> list[dict]:
    """Свои посты (новые первыми) с метриками."""
    posts: list[dict] = []
    after = None
    while len(posts) < max_posts:
        params = {"fields": POST_FIELDS, "limit": 50}
        if after:
            params["after"] = after
        page = _get(f"{API}/me/threads", token, **params)
        batch = page.get("data", [])
        if not batch:
            break
        for post in batch:
            if post.get("media_type") == "REPOST_FACADE":  # чужой пост, который вы репостнули
                continue
            posts.append({**post, **_insights(post["id"], token)})
        after = page.get("paging", {}).get("cursors", {}).get("after")
        if not after or len(batch) < 50:
            break
    return posts[:max_posts]


def save_posts(posts: list[dict], workspace: Path) -> Path:
    """JSON для программы и CSV для Excel (разделитель «;» и BOM - чтобы русский Excel открыл как надо)."""
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "threads_posts.json").write_text(
        json.dumps({"fetched_at": time.time(), "posts": posts}, ensure_ascii=False, indent=2), encoding="utf-8")
    table = workspace / "threads_posts.csv"
    columns = ["timestamp", "text", *METRICS, "media_type", "permalink"]
    with open(table, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(columns)
        for post in posts:
            writer.writerow([" ".join(str(post.get(c, "")).split()) if c == "text" else post.get(c, "")
                             for c in columns])
    return table


def load_posts(workspace: Path, max_age_hours: float | None = None) -> list[dict] | None:
    path = workspace / "threads_posts.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if max_age_hours is not None and time.time() - data["fetched_at"] > max_age_hours * 3600:
        return None
    return data["posts"]


def score(post: dict) -> int:
    """Просмотры, а если их нет - вовлечённость."""
    return post.get("views") or (post.get("likes", 0) + 3 * post.get("replies", 0) + 2 * post.get("reposts", 0))


def top_posts(posts: list[dict], count: int = 10) -> list[dict]:
    return sorted((p for p in posts if p.get("text")), key=score, reverse=True)[:count]


def describe(post: dict) -> str:
    stats = ", ".join(f"{name} {post[name]}" for name in METRICS if post.get(name))
    text = " ".join(post.get("text", "").split())
    return f"[{stats or 'нет данных'}] {text[:200]}"


def refresh(secrets, workspace: Path) -> list[dict]:
    posts = fetch_posts(ThreadsAuth(secrets).token())
    save_posts(posts, workspace)
    return posts


def ideas_context(secrets, workspace: Path) -> str:
    """Подсказка агенту идей: лучшие посты автора в Threads. Пусто, если Threads не подключён."""
    if not ThreadsAuth(secrets).is_configured():
        return ""
    posts = load_posts(workspace, max_age_hours=CACHE_HOURS)
    if posts is None:
        try:
            posts = refresh(secrets, workspace)
        except (ThreadsError, requests.RequestException) as exc:
            log.warning("Не удалось обновить статистику Threads: %s", exc)
            posts = load_posts(workspace) or []
    best = top_posts(posts)
    return "\n".join(f"- {describe(post)}" for post in best)
