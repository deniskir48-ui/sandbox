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
         "paging": {"cursors": {"after": "2"}}},
    ]
    insights = {"p1": {"views": 1200, "likes": 40, "replies": 5, "reposts": 2, "quotes": 1, "shares": 3},
                "p2": {"likes": 10, "replies": 1, "reposts": 0, "quotes": 0}, "no_views": {"p2"}}
    monkeypatch.setattr(threads.requests, "get", fake_threads_api(pages, insights, calls))

    posts = threads.fetch_posts("TOKEN")

    assert [p["id"] for p in posts] == ["p1", "p2"]  # репосты чужих постов пропущены
    assert posts[0]["views"] == 1200 and posts[1] == {**pages[1]["data"][0], **insights["p2"]}
    assert all(c[0].startswith("https://graph.threads.com/v1.0/") for c in calls)
    assert calls[0][1]["fields"] == threads.POST_FIELDS


def test_save_posts_writes_excel_friendly_csv(tmp_path):
    posts = [{"id": "p1", "text": "Line one\nline two; with semicolon", "views": 10, "likes": 2,
              "timestamp": "2026-11-01", "media_type": "TEXT_POST", "permalink": "https://threads.com/p1"}]
    table = threads.save_posts(posts, tmp_path)
    raw = table.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM - Excel распознаёт UTF-8
    rows = list(csv.reader(table.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    assert rows[0][:3] == ["timestamp", "text", "views"]
    assert rows[1][1] == "Line one line two; with semicolon"
    assert threads.load_posts(tmp_path) == posts


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
