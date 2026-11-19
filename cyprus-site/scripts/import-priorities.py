#!/usr/bin/env python3
"""Приоритеты событий из рабочей таблицы недели («… · полный отбор для воскресного дайджеста», .xlsx).

    python3 scripts/import-priorities.py import/afisha-digest.xlsx [--dry-run]

Листы «Все события» и «Рождество — полный список»: колонка «Приоритет» («1 — В первую очередь», «2 — Интересно»,
«3 — Дополнительно»), «Когда», «Событие». Событие сайта сопоставляется со строкой таблицы по дате (или попаданию
в период) и похожести названия; найденный приоритет пишется в поле priority. Сайт показывает события сначала
по приоритету, потом по дате (DEC-W45). Запускать после scripts/import-week.py и scripts/import-christmas.py —
они ставят приоритет по умолчанию.
"""
import difflib, glob, importlib.util, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "..", "src", "content", "events")
spec = importlib.util.spec_from_file_location("import_christmas", os.path.join(HERE, "import-christmas.py"))
xmas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xmas)
SHEETS = ("Все события", "Рождество — полный список")
# Названия, которые в рабочей таблице записаны иначе, чем на сайте: имя файла события → название в таблице.
ALIASES = {"pinocchio-christmas-theme-park-2026-11-21": "Открытие тематического парка «Пиноккио»"}


def norm(s):
    return re.sub(r"[^a-zа-яё0-9 ]", " ", s.lower()).split()


def similar(a, b):
    ta, tb = set(norm(a)), set(norm(b))
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(overlap, difflib.SequenceMatcher(None, " ".join(norm(a)), " ".join(norm(b))).ratio())


def main():
    import openpyxl, yaml
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    dry = "--dry-run" in sys.argv
    wb = openpyxl.load_workbook(args[0], data_only=True)
    rows = []
    for sh in SHEETS:
        if sh not in wb.sheetnames:
            continue
        for r in wb[sh].iter_rows(min_row=4, values_only=True):
            pr, when, _, title = (str(c or "").strip() for c in r[:4])
            m = re.match(r"(\d)", pr)
            parsed = xmas.parse_when(when, 2026) if title and m else None
            if parsed:
                rows.append({"p": int(m.group(1)), "date": parsed[0], "end": parsed[1], "title": title})
    week_start = min((r["date"] for r in rows if not r["end"]), default="")
    changed = matched = 0
    unmatched = []
    for path in sorted(glob.glob(os.path.join(EVENTS, "*.yaml"))):
        text = open(path, encoding="utf-8").read()
        d = yaml.safe_load(text)
        if d.get("status") != "published":
            continue
        slug = os.path.basename(path)[:-5]
        start, end = d["date"], d.get("end_date") or d["date"]
        cands = [r for r in rows if r["date"] == start or (r["end"] and r["date"] <= start <= r["end"]) or (start <= r["date"] <= end)]
        title = ALIASES.get(slug, d["title"])
        best = max(cands, key=lambda r: similar(title, r["title"]), default=None)
        if not best or similar(title, best["title"]) < 0.6:
            if end >= week_start:  # события прошлых недель в этой таблице и не должны быть
                unmatched.append(f"{d['title']} ({start})")
            continue
        matched += 1
        if d.get("priority") == best["p"]:
            continue
        new = re.sub(r"^priority: .*$", f"priority: {best['p']}", text, flags=re.M) if re.search(r"^priority:", text, re.M) \
            else re.sub(r"^(type: .*\n)", rf"\1priority: {best['p']}\n", text, count=1, flags=re.M)
        changed += 1
        if not dry:
            open(path, "w", encoding="utf-8").write(new)
    print(("[dry-run] " if dry else "") + f"сопоставлено: {matched}; приоритет изменён: {changed}; без пары в таблице: {len(unmatched)}")
    for u in unmatched[:20]:
        print("  ?", u)


if __name__ == "__main__":
    main()
