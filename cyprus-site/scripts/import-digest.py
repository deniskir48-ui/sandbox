#!/usr/bin/env python3
"""Импорт недели из рабочей таблицы «Афиша Кипра · … · полный отбор для воскресного дайджеста» (.xlsx).

    python3 scripts/import-digest.py import/afisha-digest.xlsx scripts/week-fixes/2026-11-23.json [--dry-run]

Один файл вместо двух (DEC-W46): события, приоритеты и пометки берутся из листа «Все события»
(Приоритет | Когда | Город / место | Событие | Что будет | Ссылка | В пост? | Проверка | Замечания).
Рождественские — те, что есть и в листе «Рождество — полный список»: получают метку christmas и вид
(парк, деревня, огни, ярмарка, другое) по правилам scripts/import-christmas.py.

Перед импортом каждое событие сверяется со своей страницей; решения проверки лежат в файле правок
(scripts/week-fixes/<понедельник>.json):
  skip  — строка не публикуется (уже на сайте, дубль, не подтверждено), с причиной;
  merge — строка сводится в карточку другой строки (тот же спектакль в другие дни, часть праздника);
  set   — поля, исправленные по странице события (город, время, даты, сеансы, описание таблицы…).
«Замечания» и «Проверка» — внутренние пометки редактора, на сайт не попадают (только в комментарий файла).
Файлы помечаются «# week-import»; повторный импорт их обновляет, ручные и собранные со страниц поля
(описание, адрес, цена, язык…) сохраняются (import-christmas.keep_manual). Подробности со страниц событий
дописывает scripts/enrich-apply.py; карта «строка → файл» сохраняется рядом с таблицей (*.map.json).
"""
import importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "src", "content", "events")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


week, xmas, afisha = load("import-week"), load("import-christmas"), load("import-afisha")
q, slugify, link, parse_when = xmas.q, xmas.slugify, xmas.link, xmas.parse_when
MARK = week.MARK
SHEET, XMAS_SHEET = "Все события", "Рождество — полный список"
# Поля, которые можно задать в правках, в порядке записи в файл (после summary).
EXTRA = ("open_days", "sessions", "hours", "end_time", "price")


def type_of(title, what):
    return next((t for t, rx in week.EXTRA_TYPES + afisha.TYPES if re.search(rx, f"{title} {what}", re.I)), "other")


def main():
    import openpyxl
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        sys.exit(__doc__)
    dry = "--dry-run" in sys.argv
    wb = openpyxl.load_workbook(args[0])
    fixes = json.load(open(args[1], encoding="utf-8"))
    skip, merge, sets = fixes.get("skip", {}), fixes.get("merge", {}), fixes.get("set", {})
    caption = str(wb[SHEET].cell(1, 1).value or "").strip()
    xmas_titles = {str(r[3].value).strip() for r in wb[XMAS_SHEET].iter_rows(min_row=4) if r[3].value} if XMAS_SHEET in wb.sheetnames else set()

    rows = {}
    for row in wb[SHEET].iter_rows(min_row=4):
        v = [str(c.value or "").strip() for c in row[:9]]
        if v[3]:
            rows[str(row[0].row)] = (v, link(row[5]))

    stats = {"создано": 0, "обновлено": 0, "сведено в другую карточку": 0, "не публикуется": 0, "не тронуто (ручной файл)": 0}
    mapping = {}
    for n, (v, url) in rows.items():
        if n in skip:
            stats["не публикуется"] += 1
            continue
        if n in merge:
            stats["сведено в другую карточку"] += 1
            continue
        pr, when, place, title, what, _, _, check, note = v
        fix = sets.get(n, {})
        start, end, time = parse_when(when, 2026)
        city, _, venue = place.partition(" · ")
        e = {"title": title, "date": start, "end_date": end if end and end != start else None, "time": time,
             "city": city, "venue": venue if venue and not re.search(r"уточн", venue, re.I) else None,
             "summary": week.clean(what).replace("семейский", "семейный").replace("Семейский", "Семейный"),
             "priority": int(pr[0]) if pr[:1].isdigit() else 3, "display_title": None, "type": None}
        e.update(fix)
        if e["end_date"]:
            e["time"] = e["time"] if fix.get("time") else None  # у долгих событий время — в часах/сеансах
        christmas = title in xmas_titles
        kind, etype = xmas.kind_of(e["title"], what) if christmas else (None, type_of(e["title"], what))
        etype = e["type"] or etype
        slug = f"{slugify(e['title']) or etype}-{e['date']}"
        path = os.path.join(OUT, f"{slug}.yaml")
        existing = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if existing is not None and MARK not in existing:
            stats["не тронуто (ручной файл)"] += 1
            continue
        lines = [MARK, f"# Строка {n} листа «{SHEET}» таблицы «{caption}».",
                 f"# Проверка в таблице: {check}" if check else None,
                 f"# Замечание редактора: {note}" if note else None,
                 f"# Сведено сюда: строки {', '.join(k for k, t in merge.items() if str(t) == n)}" if any(str(t) == n for t in merge.values()) else None,
                 f"title: {q(e['title'])}",
                 f"display_title: {q(e['display_title'])}" if e["display_title"] else None,
                 "status: published", f"type: {etype}", f"priority: {e['priority']}",
                 f"date: {q(e['date'])}", f"end_date: {q(e['end_date'])}" if e["end_date"] else None,
                 f"time: {q(e['time'])}" if e["time"] else None,
                 f"city: {q(e['city'])}", f"venue: {q(e['venue'])}" if e["venue"] else None,
                 f"summary: {q(e['summary'][:200])}" if e["summary"] else None]
        for k in EXTRA:
            if e.get(k):
                lines.append(f"{k}: {json.dumps(e[k], ensure_ascii=False)}")
        lines += [f"ticket_url: {q(url)}", "sources:", f"  - title: {q('Источник из таблицы афиши')}", f"    url: {q(url)}"]
        if christmas:
            lines.append(f"tags: [christmas, {kind}]")
        if existing:
            lines = xmas.keep_manual(lines, existing)
        stats["обновлено" if existing else "создано"] += 1
        mapping[n] = {"id": slug, "time": e["time"]}
        if not dry:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(l for l in lines if l is not None) + "\n")
    if not dry:
        json.dump(mapping, open(os.path.splitext(args[0])[0] + ".map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(("[dry-run] " if dry else "") + "; ".join(f"{k}: {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
