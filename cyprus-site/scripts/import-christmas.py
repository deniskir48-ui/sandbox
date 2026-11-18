#!/usr/bin/env python3
"""Импорт рождественских листов из таблицы «Афиша Кипра для Telegram» (.xlsx) в события Афиши.

    python3 scripts/import-christmas.py import/afisha-tg.xlsx [--year 2026] [--dry-run]

Листы:
  «Рождественские парки · Telegram» — Город | Парк | Даты | Часы | Что будет | Стоимость | Источник
      → события с метками christmas, christmas-parks (часы → hours, стоимость → price);
  «Рождество» — Когда | Город | Место | Мероприятие | Что будет | Источник | Проверка
      → события с меткой christmas и видом: christmas-villages, christmas-lights, christmas-markets, christmas-other.
Строки «Рождества» про те же парки пропускаются (парки берутся из своего листа).
Существующие файлы обновляются только если в них есть пометка «# christmas-import»; остальные не трогаются.
Лендинг /christmas/ собирает события по меткам; в общей Афише они тоже видны.
"""
import json, os, re, sys
import openpyxl

MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
          "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
              ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s","t","u","f","h","c","ch","sh","sch","","y","","e","yu","ya"]))
PARK = re.compile(r"fairyland|santa park fest|christmas land|пиноккио|pinocchio", re.I)
MARK = "# christmas-import"
q = lambda v: json.dumps(v, ensure_ascii=False)


def slugify(s):
    s = "".join(TR.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")


def link(cell):
    v = str(cell.value or "")
    m = re.search(r'HYPERLINK\("([^"]+)"', v)
    if m:
        return m.group(1)
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    return v if v.startswith("http") else None


def ymd(y, m, d):
    return f"{y}-{m:02d}-{d:02d}"


def parse_when(text, year):
    """'13 ноя – 10 янв · …', '20–21 ноя · 10:00', 'с 21 ноя · …', '21 ноя · с 16:30' → (start, end, time)."""
    m = re.search(r"(\d{1,2})\s+([а-я]{3})\S*\s*[–-]\s*(\d{1,2})\s+([а-я]{3})", text)
    if m:
        m1, m2 = MONTHS[m.group(2)], MONTHS[m.group(4)]
        start, end = ymd(year, m1, int(m.group(1))), ymd(year + (m2 < m1), m2, int(m.group(3)))
    else:
        m = re.search(r"(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?\s+([а-я]{3})", text)
        if not m or m.group(3) not in MONTHS:
            return None
        mo = MONTHS[m.group(3)]
        start = ymd(year, mo, int(m.group(1)))
        end = ymd(year, mo, int(m.group(2))) if m.group(2) else None
    t = re.search(r"(\d{1,2}):(\d{2})", text)
    time = f"{int(t.group(1)):02d}:{t.group(2)}" if t else None
    return start, end, time


def parse_dates(text):
    """'20.11.2026–17.01.2027' или '20–22.11.2026' → (start, end)."""
    m = re.match(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        d1, m1, y1, d2, m2, y2 = map(int, m.groups())
        return ymd(y1, m1, d1), ymd(y2, m2, d2)
    m = re.match(r"\s*(\d{1,2})\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        d1, d2, mo, y = map(int, m.groups())
        return ymd(y, mo, d1), ymd(y, mo, d2)
    return None


def kind_of(title, what):
    t, w = title.lower(), what.lower()
    if re.search(r"мастер-класс|workshop|painting", t):
        return "christmas-other", "workshop"
    if re.search(r"christmas village|рождественская деревня", t):
        return "christmas-villages", "festival"
    if re.search(r"ярмарк|маркет|market|bazaar|базар", t):
        return "christmas-markets", "festival"
    if re.search(r"зажжен|огн|ёлк|елк|lighting", t + " " + w):
        return "christmas-lights", "festival"
    if re.search(r"концерт", t):
        return "christmas-other", "concert"
    if re.search(r"спектакл|театр", t + " " + w):
        return "christmas-other", "kids"
    return "christmas-other", "festival"


def write(out, slug, lines, dry, stats):
    path = os.path.join(out, f"{slug}.yaml")
    if os.path.exists(path) and MARK not in open(path, encoding="utf-8").read():
        stats["не тронуто"] += 1
        return
    stats["обновлено" if os.path.exists(path) else "создано"] += 1
    if not dry:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(l for l in lines if l is not None) + "\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    year = int(sys.argv[sys.argv.index("--year") + 1]) if "--year" in sys.argv else 2026
    dry = "--dry-run" in sys.argv
    wb = openpyxl.load_workbook(args[0])
    out = os.path.join(os.path.dirname(__file__), "..", "src", "content", "events")
    stats = {"создано": 0, "обновлено": 0, "не тронуто": 0, "пропущено": 0}

    # Парки
    ws = wb["Рождественские парки · Telegram"]
    for row in ws.iter_rows():
        city, name, dates, hours, what, price = (str(row[i].value or "").strip() for i in range(6))
        rng = parse_dates(dates)
        url = link(row[6]) if len(row) > 6 else None
        if not name or not rng or not url:
            continue
        venue, _, rest = what.partition(":") if ":" in what else ("", "", what)
        summary = rest.strip()
        summary = summary[:1].upper() + summary[1:]
        lines = [MARK, "# Лист «Рождественские парки · Telegram» таблицы афиши (обновлено 18.11.2026).",
                 f"title: {q(name)}", "status: published", "type: festival", "priority: 2",
                 f"date: {q(rng[0])}", f"end_date: {q(rng[1])}", f"city: {q(city)}",
                 f"venue: {q(venue.strip())}" if venue.strip() else None,
                 f"summary: {q(summary[:200])}",
                 f"hours: {q(hours)}" if hours else None,
                 f"price: {q(price)}" if price else None,
                 f"ticket_url: {q(url)}", "sources:", f"  - title: {q('Источник из таблицы афиши')}", f"    url: {q(url)}",
                 "tags: [christmas, christmas-parks]"]
        write(out, f"{slugify(name)}-{rng[0]}", lines, dry, stats)

    # Праздничные события недели
    ws = wb["Рождество"]
    started = False
    for row in ws.iter_rows():
        vals = [str(c.value or "").strip() for c in row[:7]]
        if vals[0] == "Когда":
            started = True
            continue
        if not started or not vals[3]:
            continue
        when, city, venue, title, what, _, check = vals
        if PARK.search(title):
            stats["пропущено"] += 1
            continue
        parsed, url = parse_when(when, year), link(row[5])
        if not parsed or not url:
            stats["пропущено"] += 1
            print("  ! нет даты или ссылки:", title)
            continue
        start, end, time = parsed
        kind, etype = kind_of(title, what)
        lines = [MARK, "# Лист «Рождество» таблицы «Афиша Кипра для Telegram · 16–22 ноября 2026».",
                 f"# Проверка в таблице: {check}" if check else None,
                 f"title: {q(title)}", "status: published", f"type: {etype}", "priority: 3",
                 f"date: {q(start)}", f"end_date: {q(end)}" if end else None,
                 f"time: {q(time)}" if time and not end else None,
                 f"city: {q(city)}", f"venue: {q(venue)}" if venue else None,
                 f"summary: {q(what[:200])}" if what else None,
                 f"ticket_url: {q(url)}", "sources:", f"  - title: {q('Источник из таблицы афиши')}", f"    url: {q(url)}",
                 f"tags: [christmas, {kind}]"]
        write(out, f"{slugify(title) or etype}-{start}", lines, dry, stats)
    print(("[dry-run] " if dry else "") + "; ".join(f"{k}: {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
