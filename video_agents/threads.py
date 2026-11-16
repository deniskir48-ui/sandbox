"""Выгрузка своих постов из Threads со статистикой (Threads API).

Все посты и их метрики сохраняются в workspace/threads_posts.json и в таблицу Excel threads_posts.xlsx
(для аналитики), а лучшие по просмотрам получает агент идей - как подсказку, что заходит аудитории.
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API = "https://graph.threads.com/v1.0"
REFRESH_URL = "https://graph.threads.com/refresh_access_token"
REFRESH_AFTER = 7 * 24 * 3600  # ключ живёт 60 дней; продлевать можно не раньше чем через сутки
METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
BASIC_METRICS = ["likes", "replies", "reposts", "quotes"]  # views и shares Meta помечает как «в разработке»
POST_FIELDS = "id,media_type,text,permalink,timestamp"
CACHE_HOURS = 24 * 7  # для подсказок агенту идей выгрузка обновляется раз в неделю
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


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


def fetch_posts(token: str, max_posts: int | None = None) -> list[dict]:
    """Все свои посты (новые первыми) с метриками; max_posts - ограничить количество."""
    posts: list[dict] = []
    after = None
    while max_posts is None or len(posts) < max_posts:
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
        log.info("Выгружено постов: %d", len(posts))
        next_after = page.get("paging", {}).get("cursors", {}).get("after")
        if not next_after or next_after == after:  # дальше страниц нет
            break
        after = next_after
    return posts if max_posts is None else posts[:max_posts]


REPLY_FIELDS = "id,text,timestamp,root_post,replied_to"
SAVE_FORMAT = 2  # 2: посты-цепочки склеены с продолжениями


def fetch_own_replies(token: str) -> list[dict]:
    """Все ваши ответы (нужно разрешение threads_read_replies): из них собираются продолжения постов."""
    replies: list[dict] = []
    after = None
    while True:
        params = {"fields": REPLY_FIELDS, "limit": 100}
        if after:
            params["after"] = after
        page = _get(f"{API}/me/replies", token, **params)
        batch = page.get("data", [])
        replies += batch
        next_after = page.get("paging", {}).get("cursors", {}).get("after")
        if not batch or not next_after or next_after == after:
            return replies
        after = next_after


def attach_continuations(posts: list[dict], replies: list[dict]) -> list[dict]:
    """Длинный пост в Threads - цепочка ваших ответов самому себе. Склеиваем её в один текст.

    Берём только ответы, которые продолжают вашу же цепочку (ответ на сам пост или на ваше продолжение);
    ваши ответы людям в комментариях в текст поста не попадают.
    """
    by_root: dict[str, list[dict]] = {}
    for reply in replies:
        root = (reply.get("root_post") or {}).get("id")
        if root and (reply.get("text") or "").strip():
            by_root.setdefault(root, []).append(reply)
    result = []
    for post in posts:
        chain_ids = {post["id"]}
        parts = []
        for reply in sorted(by_root.get(post["id"], []), key=lambda r: r.get("timestamp", "")):
            if (reply.get("replied_to") or {}).get("id") in chain_ids:
                chain_ids.add(reply["id"])
                parts.append(reply["text"].strip())
        if parts:
            post = {**post, "text": "\n\n".join([(post.get("text") or "").strip(), *parts]),
                    "thread_parts": len(parts) + 1}
        result.append(post)
    return result


def fetch_posts_with_continuations(token: str) -> list[dict]:
    posts = fetch_posts(token)
    try:
        replies = fetch_own_replies(token)
    except ThreadsError as exc:
        log.warning("Не удалось получить продолжения постов (ваши ответы в цепочках), беру только первые "
                    "сообщения. Нужен ключ Threads с разрешением threads_read_replies: %s", exc)
        return posts
    posts = attach_continuations(posts, replies)
    joined = sum(1 for post in posts if post.get("thread_parts"))
    if joined:
        log.info("Постов-цепочек с продолжениями: %d", joined)
    return posts


COLUMNS = [  # (заголовок, ширина колонки)
    ("Дата", 12), ("Время", 8), ("День недели", 8), ("Текст", 60), ("Просмотры", 11), ("Лайки", 9),
    ("Ответы", 9), ("Репосты", 9), ("Цитаты", 9), ("Поделились", 11), ("Вовлечённость", 13), ("Тип", 12),
    ("Ссылка", 40),
]


def published_at(post: dict) -> datetime | None:
    """Время публикации по часам этого компьютера (Threads отдаёт его в UTC)."""
    try:
        return datetime.strptime(post["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone().replace(tzinfo=None)
    except (KeyError, ValueError):
        return None


def engagement(post: dict) -> float | None:
    """Доля реакций от просмотров: (лайки + ответы + репосты + цитаты + «поделились») / просмотры."""
    if not post.get("views"):
        return None
    return sum(post.get(m, 0) for m in METRICS if m != "views") / post["views"]


def save_posts(posts: list[dict], workspace: Path) -> Path:
    """JSON для программы и таблица Excel для аналитики (фильтры, закреплённая шапка, даты - датами)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "threads_posts.json").write_text(
        json.dumps({"fetched_at": time.time(), "format": SAVE_FORMAT, "posts": posts}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    book = Workbook()
    sheet = book.active
    sheet.title = "Посты Threads"
    sheet.append([title for title, _ in COLUMNS])
    for post in posts:
        moment = published_at(post)
        sheet.append([
            moment.date() if moment else None,
            moment.strftime("%H:%M") if moment else None,
            WEEKDAYS[moment.weekday()] if moment else None,
            " ".join(post.get("text", "").split()),
            *[post.get(metric) for metric in METRICS],
            engagement(post),
            post.get("media_type"),
            post.get("permalink"),
        ])
    for index, (_, width) in enumerate(COLUMNS, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in sheet.iter_rows(min_row=2):
        row[0].number_format = "DD.MM.YYYY"
        row[10].number_format = "0.00%"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    table = workspace / "threads_posts.xlsx"
    book.save(table)
    return table


def has_continuations_info(workspace: Path) -> bool:
    """Выгрузка сделана версией, которая склеивает посты-цепочки (старые выгрузки - только первые сообщения)."""
    path = workspace / "threads_posts.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("format", 1) >= SAVE_FORMAT
    except (OSError, ValueError):
        return False


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
    posts = fetch_posts_with_continuations(ThreadsAuth(secrets).token())
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


# --- Тренды Threads (Threads Trending Topics) ---
# Запросы идут от имени приложения (ключ «TH|ID|секрет»), а не пользователя. Список трендов доступен сразу,
# посты по тренду - только после одобрения Meta («advanced access»). По условиям Meta данные трендов нельзя
# передавать дальше или изменять, поэтому программа только показывает их владельцу.


class ThreadsApp:
    def __init__(self, secrets):
        self.path = Path(secrets.threads_app_file)

    def is_configured(self) -> bool:
        return self.path.exists()

    def save(self, app_id: str, app_secret: str, country: str = "US") -> list[dict]:
        """Проверяет ID и секрет пробным запросом трендов и сохраняет их."""
        token = f"TH|{app_id.strip()}|{app_secret.strip()}"
        trends = fetch_trends(token, country)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"app_id": app_id.strip(), "app_secret": app_secret.strip()}),
                             encoding="utf-8")
        return trends

    def token(self) -> str:
        if not self.path.exists():
            raise ThreadsError("Тренды не подключены: python -m video_agents auth threads-trends")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return f"TH|{data['app_id']}|{data['app_secret']}"


def fetch_trends(app_token: str, country: str = "US") -> list[dict]:
    """Текущие тренды: [{"title", "description", "trend_id"}]. Обновляются не чаще раза в час."""
    return _get(f"{API}/trending_topics", app_token, country_code=country).get("trends", [])


def fetch_trend_posts(app_token: str, trend_id: str, kind: str = "top", limit: int = 10) -> list[dict]:
    """Популярные (top) или свежие (recent) посты по тренду. Нужно одобрение Meta."""
    try:
        page = _get(f"{API}/{trend_id}/posts", app_token, trending_post_type=kind, limit=limit,
                    fields="id,username,text,permalink,timestamp,media_type")
    except ThreadsError as exc:
        raise ThreadsError("Посты по трендам Meta отдаёт только после одобрения функции "
                           f"«Threads Trending Topics» для приложения (advanced access). Ответ API: {exc}") from exc
    return page.get("data", [])


# --- Ролики из постов: какие посты переделывать и в каком порядке ---


def pick_posts(posts: list[dict], used_ids: set[str], count: int, min_views: int | None = None,
               min_age_days: float = 2, min_chars: int = 80, now: datetime | None = None) -> list[dict]:
    """Следующие посты для роликов: от старых к новым, с просмотрами не ниже порога, каждый один раз.

    Порог по умолчанию - медиана по всем постам автора (по просмотрам, а без них - по реакциям).
    Свежие посты ждут min_age_days, чтобы успеть набрать просмотры.
    """
    now = now or datetime.now()
    scores = [score(p) for p in posts if score(p) > 0]
    threshold = min_views if min_views is not None else (statistics.median(scores) if scores else 0)
    candidates = []
    for post in posts:
        moment = published_at(post)
        if (post.get("id") in used_ids or post.get("media_type") == "REPOST_FACADE"
                or len((post.get("text") or "").strip()) < min_chars
                or moment is None or now - moment < timedelta(days=min_age_days)
                or score(post) < threshold):
            continue
        candidates.append((moment, post))
    candidates.sort(key=lambda item: item[0])
    return [post for _, post in candidates[:count]]


def recent_posts(posts: list[dict], used_ids: set[str], days: float, min_chars: int = 80,
                 now: datetime | None = None) -> list[dict]:
    """Посты за последние days дней (новые первыми) - кандидаты «вне очереди», например свежие афиши."""
    now = now or datetime.now()
    fresh = []
    for post in posts:
        moment = published_at(post)
        if (moment is None or now - moment > timedelta(days=days) or post.get("id") in used_ids
                or post.get("media_type") == "REPOST_FACADE" or len((post.get("text") or "").strip()) < min_chars):
            continue
        fresh.append((moment, post))
    fresh.sort(key=lambda item: item[0], reverse=True)
    return [post for _, post in fresh]


def post_to_idea(post: dict):
    from .models import VideoIdea

    text = " ".join((post.get("text") or "").split())
    stats = ", ".join(f"{name} {post[name]}" for name in METRICS if post.get(name))
    return VideoIdea(
        viewer_problem=text[:120], relatability=10, topic=text[:80],
        angle="адаптация поста автора из Threads", hook="на усмотрение сценариста",
        why_it_works=(f"Рубрика: {post['rubric']}. " if post.get("rubric") else "")
        + f"Пост уже зашёл аудитории в Threads ({stats or 'есть отклик'})",
        source_post_id=str(post["id"]), source_text=post.get("text", ""),
    )


def load_screening(workspace: Path, niche: str = "") -> dict[str, dict]:
    """Решения отборщика по постам: {id: {"use": bool, "reason": str}}. Сменилась тема канала - решения
    устарели, проверяем заново."""
    path = workspace / "threads_screening.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["verdicts"] if data.get("niche") == niche else {}


def save_screening(workspace: Path, verdicts: dict[str, dict], niche: str = "") -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "threads_screening.json").write_text(
        json.dumps({"niche": niche, "verdicts": verdicts}, ensure_ascii=False, indent=2), encoding="utf-8")
