#!/usr/bin/env python3
"""Импорт недельной таблицы афиши (Google Sheets → Файл → Скачать → .xlsx) в черновики событий.

    pip install openpyxl
    python3 scripts/import-afisha.py import/afisha.xlsx [--year 2026]

Ожидаемые колонки листа «Все события» (как в «Афиша Кипра · 9–15 ноября 2026»):
  A приоритет («1 — В первую очередь» → priority: 1) · B когда («14–15 ноя · 20:00») · C «город · место» · D событие · E что будет
  F ссылка (=HYPERLINK) · G в пост? · H проверка · I замечания
Создаёт src/content/events/<slug>.yaml со status: published (события проверяются при составлении таблицы). Существующие файлы не трогает.
Пропускает строки, помеченные как дубли («объединить», «уже есть общ…», «не делать дубли»)
и с запретом на публикацию («НЕ включать»). Замечания редактора пишутся комментарием в файл,
на сайт они не попадают.
"""
import json, os, re, sys
import openpyxl

MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
          "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
              ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s","t","u","f","h","c","ch","sh","sch","","y","","e","yu","ya"]))

# Порядок важен: первое совпадение определяет тип.
TYPES = [
    ("standup", r"стендап|stand-?up"),
    ("sport", r"марафон|забег|регат|заплыв|велонедел|endurance|\brace\b|\brun\b|swim"),
    ("cinema", r"кино|фильм|cinema|screening|movie"),
    ("kids", r"детск|для детей|малыш|семейн|little ones|kids|шапочк|снежная королева"),
    ("workshop", r"мастер-класс|мастерск|workshop|занятие по|sip & paint|pasta makers|ceramics|своими руками|плетение|перегонк"),
    ("festival", r"фестивал|festival|fest\b|ярмарк|market|рынок|огни|огней|ёлки"),
    ("exhibition", r"выставк|expo|show 2026"),
    ("theatre", r"спектакл|постановк|театр|комеди|шоу|fashion"),
    ("talk", r"лекци|конференц|summit|встреч|книжный клуб|знакомств|singles"),
    ("party", r"вечеринк|party|клубн|electronic|электронн"),
    ("tour", r"поход|прогулк|маршрут|birdwatching|поездк|walk"),
    ("concert", r"концерт|джаз|jazz|metal|метал|рок|певец|певиц|исполнител|музык|\blive\b|jam|dj|фронтмен"),
]
SKIP = re.compile(r"объединить|уже есть общ|не делать дубли|НЕ включать", re.I)


def slugify(s):
    s = "".join(TR.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")


def parse_when(text, year):
    """'14–15 ноя · 20:00' → ('2026-11-14', '2026-11-15', '20:00')."""
    m = re.search(r"(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?\s+([а-я]{3})", text)
    if not m:
        return None
    month = MONTHS.get(m.group(3))
    if not month:
        return None
    start = f"{year}-{month:02d}-{int(m.group(1)):02d}"
    end = f"{year}-{month:02d}-{int(m.group(2)):02d}" if m.group(2) else None
    t = re.search(r"(\d{1,2}):(\d{2})", text)
    time = f"{int(t.group(1)):02d}:{t.group(2)}" if t else None
    return start, end, time


def link(cell):
    v = str(cell.value or "")
    m = re.search(r'HYPERLINK\("([^"]+)"', v)
    if m:
        return m.group(1)
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    return v if v.startswith("http") else None


def q(v):  # строка в YAML: JSON-строка — валидный YAML
    return json.dumps(v, ensure_ascii=False)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    path = args[0]
    year = int(args[args.index("--year") + 1]) if "--year" in args else 2026
    out = os.path.join("src", "content", "events")
    os.makedirs(out, exist_ok=True)

    ws = openpyxl.load_workbook(path)["Все события"]
    created = skipped = exists = bad = 0
    for row in ws.iter_rows(min_row=4):
        when, place, title, what = (str(row[i].value or "").strip() for i in (1, 2, 3, 4))
        note, check = str(row[8].value or "").strip(), str(row[7].value or "").strip()
        if not title:
            continue
        if SKIP.search(note):
            skipped += 1
            continue
        parsed, url = parse_when(when, year), link(row[5])
        if not parsed or not url:
            bad += 1
            print(f"  ! пропущено (нет даты или ссылки): {title}")
            continue
        start, end, time = parsed
        city, _, venue = place.partition(" · ")
        hay = f"{title} {what}".lower()
        pm = re.match(r"\s*(\d)", str(row[0].value or ""))
        priority = int(pm.group(1)) if pm else 3
        etype = next((t for t, rx in TYPES if re.search(rx, hay, re.I)), "other")

        slug = f"{slugify(title) or slugify(etype)}-{start}"  # названия на греческом и т. п. → по типу
        file = os.path.join(out, f"{slug}.yaml")
        if os.path.exists(file):
            exists += 1
            continue
        lines = [
            "# Из недельной таблицы афиши (события проверены при её составлении).",
            f"# Проверка в таблице: {check}" if check else None,
            f"# Замечание редактора: {note}" if note else None,
            f"title: {q(title)}",
            "status: published",
            f"type: {etype}",
            f"priority: {priority}",
            f"date: {q(start)}",
            f"end_date: {q(end)}" if end else None,
            f"time: {q(time)}" if time and not end else None,
            f"city: {q(city.strip())}",
            f"venue: {q(venue.strip())}" if venue.strip() else None,
            f"summary: {q(what[:200])}" if what else None,
            f"ticket_url: {q(url)}",
            "sources:",
            f"  - title: {q('Ссылка из таблицы афиши')}",
            f"    url: {q(url)}",
        ]
        with open(file, "w", encoding="utf-8") as f:
            f.write("\n".join(l for l in lines if l is not None) + "\n")
        created += 1
    print(f"Создано черновиков событий: {created}; уже были: {exists}; пропущено дублей/запретов: {skipped}; без даты/ссылки: {bad}")


if __name__ == "__main__":
    main()
