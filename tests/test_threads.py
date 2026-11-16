import csv
import json
import time

import pytest

from video_agents import threads
from video_agents.config import Secrets


class Response:
    def __init__(self, payload, ok=True):
        self.payload, self.ok, self.status_code = payload, ok, 200 if ok else 400

    def json(self):
        return self.payload


def fake_threads_api(posts_pages, insights, calls):
    def get(url, params, timeout):
        calls.append((url, dict(params)))
        if url.endswith("/me"):
            return Response({"id": "u1", "username": "denis.strength"})
        if url.endswith("/me/threads"):
            page = posts_pages[0 if "after" not in params else int(params["after"])]
            return Response(page)
        media_id = url.split("/")[-2]
        metrics = params["metric"].split(",")
        if "views" in metrics and media_id in insights.get("no_views", set()):
            return Response({"error": {"message": "metric views not available"}}, ok=False)
        values = insights[media_id]
        return Response({"data": [{"name": m, "period": "lifetime", "values": [{"value": values[m]}]}
                                  for m in metrics if m in values]})
    return get


def test_fetch_posts_with_insights_and_pagination(monkeypatch):
    calls = []
    pages = [
        {"data": [{"id": "p1", "media_type": "TEXT_POST", "text": "Belly fat myth", "timestamp": "t1"}] * 1
         + [{"id": f"x{i}", "media_type": "REPOST_FACADE"} for i in range(49)],
         "paging": {"cursors": {"after": "1"}}},
        {"data": [{"id": "p2", "media_type": "VIDEO", "text": "Protein timing", "timestamp": "t2"}],
         "paging": {"cursors": {"before": "1"}}},  # последняя страница: курсора «дальше» нет
    ]
    insights = {"p1": {"views": 1200, "likes": 40, "replies": 5, "reposts": 2, "quotes": 1, "shares": 3},
                "p2": {"likes": 10, "replies": 1, "reposts": 0, "quotes": 0}, "no_views": {"p2"}}
    monkeypatch.setattr(threads.requests, "get", fake_threads_api(pages, insights, calls))

    posts = threads.fetch_posts("TOKEN")

    assert [p["id"] for p in posts] == ["p1", "p2"]  # репосты чужих постов пропущены
    assert posts[0]["views"] == 1200 and posts[1] == {**pages[1]["data"][0], **insights["p2"]}
    assert all(c[0].startswith("https://graph.threads.com/v1.0/") for c in calls)
    assert calls[0][1]["fields"] == threads.POST_FIELDS


def test_save_posts_writes_excel_table(tmp_path):
    from datetime import date

    from openpyxl import load_workbook

    posts = [{"id": "p1", "text": "Line one\nline two", "views": 200, "likes": 10, "replies": 4, "reposts": 2,
              "quotes": 0, "shares": 4, "timestamp": "2026-11-02T10:15:00+0000", "media_type": "TEXT_POST",
              "permalink": "https://threads.com/p1"},
             {"id": "p2", "text": "No stats", "timestamp": "bad", "media_type": "VIDEO"}]
    table = threads.save_posts(posts, tmp_path)
    assert table.name == "threads_posts.xlsx"

    sheet = load_workbook(table).active
    assert [c.value for c in sheet[1]][:5] == ["Дата", "Время", "День недели", "Текст", "Просмотры"]
    row = [c.value for c in sheet[2]]
    moment = threads.published_at(posts[0])
    assert row[0].date() == moment.date() and row[1] == moment.strftime("%H:%M")
    assert row[2] == threads.WEEKDAYS[moment.weekday()] and moment.date() in (date(2026, 11, 2), date(2026, 11, 1))
    assert row[3] == "Line one line two" and row[4] == 200
    assert row[10] == 0.1  # (10 + 4 + 2 + 0 + 4) / 200
    assert sheet["K2"].number_format == "0.00%" and sheet.freeze_panes == "A2" and sheet.auto_filter.ref
    assert [c.value for c in sheet[3]][:4] == [None, None, None, "No stats"]  # кривая дата не ломает выгрузку
    assert threads.load_posts(tmp_path) == posts


def test_fetch_all_posts_until_last_page(monkeypatch):
    pages = {None: {"data": [{"id": "a", "text": "1"}], "paging": {"cursors": {"after": "c1"}}},
             "c1": {"data": [{"id": "b", "text": "2"}], "paging": {"cursors": {"after": "c2"}}},
             "c2": {"data": [{"id": "c", "text": "3"}], "paging": {"cursors": {"after": "c2"}}}}
    monkeypatch.setattr(threads, "_get", lambda url, token, **params: pages[params.get("after")]
                        if url.endswith("/me/threads") else {"data": []})
    assert [p["id"] for p in threads.fetch_posts("T")] == ["a", "b", "c"]
    assert [p["id"] for p in threads.fetch_posts("T", max_posts=2)] == ["a", "b"]


def test_ideas_context_uses_fresh_cache_and_top_posts(tmp_path, monkeypatch):
    secrets = Secrets(threads_token_file=str(tmp_path / "t.json"))
    assert threads.ideas_context(secrets, tmp_path) == ""  # не подключён

    (tmp_path / "t.json").write_text(json.dumps({"access_token": "T", "user_id": "u", "saved_at": time.time()}))
    posts = [{"id": str(i), "text": f"post {i}", "views": i * 100} for i in range(15)]
    threads.save_posts(posts, tmp_path)
    monkeypatch.setattr(threads, "fetch_posts", lambda token: pytest.fail("кэш свежий - API не нужен"))
    context = threads.ideas_context(secrets, tmp_path)
    lines = context.splitlines()
    assert len(lines) == 10 and "post 14" in lines[0] and "views 1400" in lines[0]


def test_token_saved_and_refreshed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(threads.requests, "get", lambda url, params, timeout: calls.append(url) or Response(
        {"id": "u1", "username": "denis.strength"} if url.endswith("/me") else {"access_token": "NEW"}))
    auth = threads.ThreadsAuth(Secrets(threads_token_file=str(tmp_path / "t.json")))
    assert auth.save(" OLD \n")["username"] == "denis.strength"
    assert auth.token() == "OLD"
    monkeypatch.setattr(threads.time, "time", lambda: 10**12)
    assert auth.token() == "NEW" and calls[-1] == threads.REFRESH_URL


TRENDS = {"trends": [
    {"title": "Ozempic and muscle loss", "description": "People debate...", "trend_id": "9876543210123456"},
    {"title": "Marathon season", "trend_id": "1111"},
]}


def test_trends_use_app_token_and_country(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, token, **params):
        calls.append((url, token, params))
        return TRENDS

    monkeypatch.setattr(threads, "_get", fake_get)
    app = threads.ThreadsApp(Secrets(threads_app_file=str(tmp_path / "app.json")))
    assert not app.is_configured()
    assert [t["title"] for t in app.save(" 123 ", "s3cret\n", "US")] == ["Ozempic and muscle loss", "Marathon season"]
    assert calls[0] == ("https://graph.threads.com/v1.0/trending_topics", "TH|123|s3cret", {"country_code": "US"})
    assert app.token() == "TH|123|s3cret"


def test_trend_posts_explain_missing_approval(monkeypatch):
    def denied(url, token, **params):
        assert url.endswith("/9876543210123456/posts") and params["trending_post_type"] == "top"
        raise threads.ThreadsError("Threads API: Application does not have permission for this action")

    monkeypatch.setattr(threads, "_get", denied)
    with pytest.raises(threads.ThreadsError, match="одобрения"):
        threads.fetch_trend_posts("TH|1|2", "9876543210123456")


def _post(pid, days_ago, views, text="Пост достаточно длинный, чтобы из него получился ролик: " * 2):
    from datetime import datetime, timedelta, timezone

    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {"id": pid, "text": text, "views": views, "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "media_type": "TEXT_POST"}


def test_pick_posts_oldest_first_above_median_once():
    posts = [_post("new", 0.5, 5000), _post("mid", 30, 3000), _post("old", 400, 3500), _post("weak", 200, 10),
             _post("weak2", 210, 10), _post("weak3", 220, 10), _post("short", 300, 5000, text="коротко"),
             _post("used", 500, 9000), _post("older", 450, 600)]
    # медиана по всем постам = 3000 → «weak*» и «older» (600) не проходят; «new» ещё слишком свежий
    picked = threads.pick_posts(posts, used_ids={"used"}, count=5)
    assert [p["id"] for p in picked] == ["old", "mid"]
    assert [p["id"] for p in threads.pick_posts(posts, {"used"}, 5, min_views=500)] == ["older", "old", "mid"]
    assert [p["id"] for p in threads.pick_posts(posts, {"used"}, 5, min_age_days=0)][-1] == "new"


def test_post_to_idea_keeps_source():
    idea = threads.post_to_idea({"id": 42, "text": "Жираф по-гречески", "views": 467000, "likes": 9000})
    assert idea.source_post_id == "42" and idea.source_text == "Жираф по-гречески"
    assert "views 467000" in idea.why_it_works


def test_thread_chains_are_glued_but_replies_to_people_are_not():
    posts = [{"id": "root", "text": "Аптеки на Кипре работают не всегда."},
             {"id": "solo", "text": "Короткий пост без продолжения"}]
    replies = [
        # Порядок из API не важен: склеиваем по времени.
        {"id": "r2", "text": "Список дежурных - на сайте Минздрава.", "timestamp": "2026-11-01T10:02:00+0000",
         "root_post": {"id": "root"}, "replied_to": {"id": "r1"}},
        {"id": "r1", "text": "Но всегда есть дежурная аптека.", "timestamp": "2026-11-01T10:01:00+0000",
         "root_post": {"id": "root"}, "replied_to": {"id": "root"}},
        # Ваш ответ комментатору под этим постом - не продолжение.
        {"id": "c1", "text": "Спасибо!", "timestamp": "2026-11-01T12:00:00+0000",
         "root_post": {"id": "root"}, "replied_to": {"id": "someone_comment"}},
        # Ответ под чужим постом.
        {"id": "x1", "text": "Согласен", "timestamp": "2026-11-01T12:00:00+0000",
         "root_post": {"id": "other"}, "replied_to": {"id": "other"}},
    ]
    glued = threads.attach_continuations(posts, replies)
    assert glued[0]["text"] == ("Аптеки на Кипре работают не всегда.\n\nНо всегда есть дежурная аптека.\n\n"
                                "Список дежурных - на сайте Минздрава.")
    assert glued[0]["thread_parts"] == 3
    assert glued[1] == posts[1]


def test_without_reply_permission_posts_still_load(monkeypatch):
    monkeypatch.setattr(threads, "fetch_posts", lambda token: [{"id": "a", "text": "Первая часть"}])

    def denied(url, token, **params):
        raise threads.ThreadsError("Threads API: permission threads_read_replies required")

    monkeypatch.setattr(threads, "_get", denied)
    assert threads.fetch_posts_with_continuations("T") == [{"id": "a", "text": "Первая часть"}]


def test_old_export_without_chains_is_refetched(tmp_path):
    import json

    (tmp_path / "threads_posts.json").write_text(json.dumps({"fetched_at": 0, "posts": []}), encoding="utf-8")
    assert not threads.has_continuations_info(tmp_path)
    threads.save_posts([], tmp_path)
    assert threads.has_continuations_info(tmp_path)
