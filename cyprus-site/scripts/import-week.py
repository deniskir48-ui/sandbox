#!/usr/bin/env python3
"""Импорт недельной афиши из листа «Все мероприятия» таблицы «Афиша Кипра для Telegram» (.xlsx) в события Афиши.

    python3 scripts/import-week.py import/afisha-tg.xlsx [--year 2026] [--dry-run]

Колонки листа: Когда | Город / район | Место | Мероприятие | Что будет / важные детали | Источник ↗ | Проверка
(как в листе «Рождество», поэтому разбор дат, ссылок и пометок — общий с scripts/import-christmas.py).

- Рождественские события, уже заведённые из листов «Рождество» и «Рождественские парки», не дублируются:
  совпадает файл (название + дата) или это рождественский парк.
- Строки с пометкой «не включать» пропускаются; тип события — по ключевым словам, как в scripts/import-afisha.py.
- Служебные пометки таблицы на сайт не попадают: «✓ Афиша», «◒ …», «· Греческий язык» (ненадёжная автометка),
  «понижаем», «можно не выносить в пост»; «уточнить / проверить / сверить» переписываются для читателя
  («Уточняйте язык и формат», «время уточняйте у организатора»). Место «уточнить» не пишется.
- Файлы помечаются «# week-import» и обновляются при повторном импорте; без пометки — не трогаются.
  Понятное название (display_title), заданное вручную, сохраняется.
"""
import importlib.util, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


xmas, afisha = load("import-christmas"), load("import-afisha")
q, slugify, link, parse_when, for_reader = xmas.q, xmas.slugify, xmas.link, xmas.parse_when, xmas.for_reader
MARK = "# week-import"
SHEET = "Все мероприятия"

# Служебные пометки таблицы: убираются или переписываются до общих правил for_reader.
NOTES = [
    (r"\s*[✓◒][^·]*", ""),                                   # «✓ Афиша», «◒ Афиша / проверить 22.11» — до « · » или конца
    (r"\s*·\s*(?:Греческий язык|Язык:\s*\S+)", ""),          # автометка языка, часто противоречит описанию
    (r"\.?\s*Грекоязычная, понижаем\.?", "."),
    (r",\s*понижаем\b", ""),
    (r":\s*можно не выносить отдельной строкой в пост", ""),
    (r"Объединены [^;.]*[;.]?\s*", ""),
    (r"\s*Площадка именно [^.]*\.?", ""),
    (r"Общий календарь Fever указывает .*", "Время сеанса уточняйте при покупке билета."),
    (r"в источниках, сверить с продавцом", "— уточняйте у продавца"),
    (r"Проверить цену, некоторые источники показывают свободный вход", "Цену уточняйте у организатора: по некоторым данным вход свободный"),
    (r"\bв части афиш\b", "по некоторым данным"),
    (r"\bуточнять у\b", "уточняйте у"),
]
# Уточнения к типам из scripts/import-afisha.py — проверяются первыми (то, что там уходило в «Другое»).
EXTRA_TYPES = [
    ("concert", r"оркестр|orchestra|пианист|candlelight|квартет|мелодик-техно|вокальный вечер"),
    ("talk", r"конгресс|congress|семинар|seminar|форум|forum|деловой|нетворкинг|networking|business breakfast|викторин|quiz|blind test|дискусси|стартап"),
    ("tour", r"экскурси|\btour\b|enduro|эндуро"),
    ("sport", r"гольф|golf|tai chi|танцевальный конкурс|dance competition"),
    ("festival", r"bazaar|барахолк|christmas village|рождественская площадка|beaujolais|дегустац|нард"),
]
VERB = r"(?:нужно\s+)?(?:уточнить|проверить|перепроверить|сверить)"


def clean(text):
    for rx, rep in NOTES:
        text = re.sub(rx, rep, text)
    text = for_reader(text)
    # «X уточнить» в конце фразы → «X уточняйте у организатора»; «Уточнить X» → «Уточняйте X».
    text = re.sub(r"(^|[.;,]\s*)([^.;,]*?\S)\s+" + VERB + r"(?=$|[.;,])", r"\1\2 уточняйте у организатора", text)
    text = re.sub(r"\b(?:Уточнить|Сверить)\s+", "Уточняйте ", text)
    text = re.sub(r"\b(?:уточнить|сверить)\s+", "уточняйте ", text)
    text = re.sub(r"\b(?:Проверить|Перепроверить)\s+", "Проверяйте ", text)
    text = re.sub(r"\b(?:проверить|перепроверить)\s+", "проверяйте ", text)
    text = re.sub(r"у организатора у ", "у ", text)
    return for_reader(text)


def main():
    import openpyxl
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    year = int(sys.argv[sys.argv.index("--year") + 1]) if "--year" in sys.argv else 2026
    dry = "--dry-run" in sys.argv
    wb = openpyxl.load_workbook(args[0])
    title_cell = str(wb[SHEET].cell(1, 1).value or "").strip()
    out = os.path.join(HERE, "..", "src", "content", "events")
    stats = {"создано": 0, "обновлено": 0, "уже есть (Рождество и др.)": 0, "не включать": 0, "без даты/ссылки": 0}
    started = False
    for row in wb[SHEET].iter_rows():
        vals = [str(c.value or "").strip() for c in row[:7]]
        if vals[0] == "Когда":
            started = True
            continue
        if not started or not vals[3]:
            continue
        when, city, venue, title, what, _, check = vals
        if afisha.SKIP.search(what) or afisha.SKIP.search(check):
            stats["не включать"] += 1
            continue
        if xmas.PARK.search(title):
            stats["уже есть (Рождество и др.)"] += 1
            continue
        parsed, url = parse_when(when, year), link(row[5])
        if not parsed or not url:
            stats["без даты/ссылки"] += 1
            print("  ! нет даты или ссылки:", title)
            continue
        start, end, time = parsed
        etype = next((t for t, rx in EXTRA_TYPES + afisha.TYPES if re.search(rx, f"{title} {what}", re.I)), "other")
        slug = f"{slugify(title) or etype}-{start}"
        path = os.path.join(out, f"{slug}.yaml")
        existing = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if existing is not None and MARK not in existing:
            stats["уже есть (Рождество и др.)"] += 1
            continue
        summary = clean(what)
        lines = [MARK, f"# Лист «{SHEET}» таблицы «{title_cell or 'Афиша Кипра для Telegram'}».",
                 f"# Проверка в таблице: {check}" if check else None,
                 f"# Как в таблице: {what}" if what and what != summary else None,
                 f"title: {q(title)}"]
        if existing:
            lines += [l for l in existing.splitlines() if l.startswith("display_title:")]
        lines += ["status: published", f"type: {etype}", "priority: 3",
                  f"date: {q(start)}", f"end_date: {q(end)}" if end and end != start else None,
                  f"time: {q(time)}" if time and not (end and end != start) else None,
                  f"city: {q(city)}",
                  f"venue: {q(venue)}" if venue and not re.search(r"уточн", venue, re.I) else None,
                  f"summary: {q(summary[:240])}" if summary else None,
                  f"ticket_url: {q(url)}", "sources:", f"  - title: {q('Источник из таблицы афиши')}", f"    url: {q(url)}"]
        stats["обновлено" if existing else "создано"] += 1
        if not dry:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(l for l in lines if l is not None) + "\n")
    print(("[dry-run] " if dry else "") + "; ".join(f"{k}: {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
