#!/usr/bin/env python3
"""Импорт листа «Карточки сайта — исследование» из единой базы (Google Sheets → Файл → Скачать → .xlsx).

    pip install openpyxl
    python3 scripts/import-research.py import/catalog.xlsx [--dry-run]

Обновляет черновики в src/content/companies/ по колонке ID (= source_id). Раздел и подкатегории
не трогает: в таблице старые категории, на сайте — своя таксономия (src/data/taxonomy.ts).

Какие карточки НЕ трогает (ручная работа на сайте важнее таблицы):
  - опубликованные (status: published);
  - проверенные вручную (есть verified_at, но нет пометки «# research-import»);
  - с доп. подкатегориями (extra_categories), с отметкой Verified, без source_id.

Что берёт из таблицы (только публичное): описание до 150 символов → summary, детальное описание → description,
услуги → services, условия / цены / бронирование → conditions, адрес → address, город / охват → city,
официальный сайт → website (если нет — первая соцсеть → channel), проверенные источники (только ссылки) → sources.
Статус «Исследовано: нужна редакторская проверка» → verified_at = дата исследования (карточка ждёт утверждения
владельцем, status остаётся draft). «Дополнительная проверка обязательна» — данные заполняются, но verified_at нет.
«Не подтверждено» — карточка не меняется, только заметка.

На сайт НЕ попадают: «Что стоит учесть», «Что ещё проверить», «Редакционная заметка» (это указания редактору —
пишутся комментариями в файл), публичные телефоны и email (решение владельца — DEC-W35).
"""
import json, os, re, sys
from urllib.parse import urlparse
import openpyxl

SHEET = "Карточки сайта — исследование"
ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "content", "companies")
MARK = "# research-import"
COLS = ["id", "category", "subcategory", "name", "city", "summary", "description", "services", "conditions",
        "caveats", "address", "website", "phone", "email", "social", "sources", "date", "status", "todo", "note"]

q = lambda s: json.dumps(s, ensure_ascii=False)
URL = re.compile(r"https?://[^\s;,]+")


def read_rows(path):
    ws = openpyxl.load_workbook(path, data_only=True)[SHEET]
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        row = dict(zip(COLS, [("" if c is None else str(c).strip()) for c in r]))
        if re.match(r"^[A-Z]+-\d+$", row["id"]):
            out[row["id"]] = row
    return out


def existing():
    files = {}
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".yaml"):
            continue
        p = os.path.join(ROOT, f)
        txt = open(p, encoding="utf-8").read()
        m = re.search(r"^source_id:\s*(\S+)", txt, re.M)
        if m:
            files.setdefault(m.group(1), []).append((p, txt))
    return files


def protected(txt):
    if re.search(r"^status:\s*published", txt, re.M):
        return "опубликована"
    if re.search(r"^(extra_categories|verified_badge):", txt, re.M):
        return "ручные уточнения на сайте"
    if re.search(r"^verified_at:", txt, re.M) and MARK not in txt:
        return "проверена вручную"
    return None


def field(txt, name):
    m = re.search(rf"^{name}:\s*(.+)$", txt, re.M)
    if not m:
        return None
    v = m.group(1).strip()
    if v.startswith('"'):
        return json.loads(v)
    return v


def clean_url(u):
    return u.rstrip(".)")


def source_title(url, website):
    p = urlparse(url)
    host = p.netloc.replace("www.", "")
    if website and urlparse(website).netloc.replace("www.", "") == host:
        path = p.path.strip("/")
        return f"Официальный сайт — {host}" + (f"/{path}" if path else "")
    return host + (p.path.rstrip("/") if len(p.path) > 1 else "")


def channel_label(url):
    host = urlparse(url).netloc.replace("www.", "")
    handle = urlparse(url).path.strip("/").split("/")[0]
    names = {"instagram.com": "Instagram", "facebook.com": "Facebook", "t.me": "Telegram", "threads.com": "Threads",
             "threads.net": "Threads", "tiktok.com": "TikTok", "linktr.ee": "Linktree", "youtube.com": "YouTube"}
    name = names.get(host, host)
    return f"{name} {handle}".strip() if handle else name


def build(old, r):
    """Новый текст карточки: служебные поля — из старого файла, публичные — из таблицы."""
    keep = {k: field(old, k) for k in ["name", "section", "category", "network", "service_type", "languages", "source_id"]}
    ready = r["status"].startswith("Исследовано: нужна редакторская")
    website = clean_url(URL.findall(r["website"])[0]) if URL.findall(r["website"]) else None
    socials = [clean_url(u) for u in URL.findall(r["social"])]
    sources = []
    for u in [clean_url(u) for u in URL.findall(r["sources"])]:
        if u not in [s[1] for s in sources]:
            sources.append((source_title(u, website), u))
    city = re.sub(r"\s*;\s*", ", ", r["city"]) or field(old, "city")
    services = [s.strip()[0].upper() + s.strip()[1:] for s in r["services"].split(";") if s.strip()]

    L = [MARK,
         f"# Данные — лист «{SHEET}» единой базы, исследование {r['date']} ({r['status']}). Claude их не перепроверял.",
         "# Ждёт утверждения владельцем — до этого status: draft." if ready else
         "# НЕ проверено: по таблице нужна дополнительная проверка — без verified_at карточку нельзя опубликовать."]
    for label, key in [("Что стоит учесть", "caveats"), ("Что ещё проверить", "todo"), ("Заметка редактора", "note")]:
        if r[key]:
            L.append(f"# {label}: {r[key]}")
    L += [f"name: {q(keep['name'])}", "status: draft", f"section: {keep['section']}", f"category: {keep['category']}"]
    if city:
        L.append(f"city: {q(city)}")
    for k in ["network", "service_type", "languages"]:
        if keep[k]:
            L.append(f"{k}: {q(keep[k])}")
    if r["summary"]:
        L.append(f"summary: {q(r['summary'][:160])}")
    if r["description"]:
        L.append(f"description: {q(r['description'])}")
    if services:
        L.append("services:")
        L += [f"  - {q(s)}" for s in services]
    if r["conditions"]:
        L.append(f"conditions: {q(r['conditions'])}")
    if r["address"]:
        L.append(f"address: {q(r['address'])}")
    if website:
        L.append(f"website: {q(website)}")
    if socials and not website:
        L += ["channel:", f"  label: {q(channel_label(socials[0]))}", f"  url: {q(socials[0])}"]
    if sources:
        L.append("sources:")
        for t, u in sources:
            L += [f"  - title: {q(t)}", f"    url: {q(u)}"]
    else:
        L.append("sources: []")
    if ready and sources and re.match(r"^\d{4}-\d{2}-\d{2}$", r["date"]):
        L.append(f"verified_at: {r['date']}")
    L.append(f"source_id: {keep['source_id']}")
    return "\n".join(L) + "\n"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    rows, files = read_rows(args[0]), existing()
    stats = {"обновлено": 0, "проверено (ждёт утверждения)": 0, "без проверки": 0, "не подтверждено": 0, "защищено": 0, "нет файла": 0}
    skipped = []
    for rid, r in rows.items():
        if rid not in files:
            stats["нет файла"] += 1
            skipped.append(f"{rid} {r['name']}: нет карточки на сайте")
            continue
        for path, old in files[rid]:
            why = protected(old)
            if why:
                stats["защищено"] += 1
                skipped.append(f"{rid} {os.path.basename(path)}: {why}")
                continue
            if r["status"].startswith("Не подтверждено"):
                stats["не подтверждено"] += 1
                continue
            new = build(old, r)
            stats["обновлено"] += 1
            stats["проверено (ждёт утверждения)" if "verified_at:" in new else "без проверки"] += 1
            if not dry and new != old:
                open(path, "w", encoding="utf-8").write(new)
    print(("[dry-run] " if dry else "") + "; ".join(f"{k}: {v}" for k, v in stats.items()))
    for s in skipped:
        print("  пропущено —", s)


if __name__ == "__main__":
    main()
