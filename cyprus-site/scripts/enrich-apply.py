#!/usr/bin/env python3
"""Дописывает в события подробности, собранные со страниц источников (описание, время окончания, цена, адрес…).

    python3 scripts/enrich-apply.py results.json [--dry-run]

results.json — массив объектов, по одному на событие (так отвечает проверка страниц источников):
  {"id": "<имя файла события без .yaml>", "pages": [...], "description_ru": "...", "start": "HH:MM", "end": "HH:MM",
   "price": "...", "address": "...", "language": "...", "age": "...", "booking": "...", "other_dates": "...", "conflict": "..."}

Правила (DEC-W44):
- пишется только то, что есть на странице: пустые значения пропускаются, уже заполненные поля не перезаписываются;
- время начала не меняется: если оно расходится с афишей — это «конфликт», его показывает отчёт, а не сайт;
- время окончания пишется только для однодневных событий, у которых время начала совпало;
- у долгих событий (парки, деревни) «start–end» становится часами работы, если их не было;
- прочитанные страницы добавляются в источники («Страница события»).
Поля сохраняются при повторном импорте таблицы (scripts/import-christmas.py keep_manual).
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "..", "src", "content", "events")
q = lambda v: json.dumps(v, ensure_ascii=False)
TIME = re.compile(r"^\d{2}:\d{2}$")


def field(text, key):
    m = re.search(rf"^{key}: (.*)$", text, re.M)
    return json.loads(m.group(1)) if m and m.group(1).startswith('"') else (m.group(1) if m else None)


def clean(v):
    if v is None:
        return None
    v = re.sub(r"\s+", " ", str(v)).strip().rstrip(".") if not isinstance(v, str) or len(v) < 400 else str(v).strip()
    return v or None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    dry = "--dry-run" in sys.argv
    data = json.load(open(args[0], encoding="utf-8"))
    changed, conflicts, missing = 0, [], []
    for r in data:
        path = os.path.join(EVENTS, f"{r['id']}.yaml")
        if not os.path.exists(path):
            missing.append(r["id"])
            continue
        text = open(path, encoding="utf-8").read()
        lines = text.splitlines()
        has = lambda k: re.search(rf"^{k}:", text, re.M) is not None
        long = has("end_date") and field(text, "end_date") != field(text, "date")
        add = []
        desc = clean(r.get("description_ru"))
        if desc and not has("description"):
            add.append(f"description: {q(desc if desc.endswith(('.', '!', '?', '»')) else desc + '.')}")
        start, end = clean(r.get("start")), clean(r.get("end"))
        cur = field(text, "time")
        if start and cur and start != cur:
            conflicts.append(f"{r['id']}: время в афише {cur}, на странице {start}")
        if long:
            if start and end and TIME.match(start) and TIME.match(end) and not has("hours"):
                add.append(f"hours: {q(f'{start}–{end}')}")
        elif end and TIME.match(end) and not has("end_time") and (not cur or cur == start):
            add.append(f"end_time: {q(end)}")
        for src, key in (("price", "price"), ("address", "address"), ("language", "language"), ("age", "age"),
                         ("booking", "booking"), ("other_dates", "more_dates")):
            v = clean(r.get(src))
            if v and not has(key):
                add.append(f"{key}: {q(v[:1].upper() + v[1:])}")
        if r.get("conflict"):
            conflicts.append(f"{r['id']}: {r['conflict']}")
        known = set(re.findall(r'url: "([^"]+)"', text))
        new_src = []
        for u in r.get("pages") or []:
            if u and u not in known and u.startswith("http"):
                new_src += [f"  - title: {q('Страница события')}", f"    url: {q(u)}"]
                known.add(u)
        if not add and not new_src:
            continue
        j = next((i for i, l in enumerate(lines) if l.startswith("ticket_url:")), len(lines))
        lines = lines[:j] + add + lines[j:]
        if new_src:
            e = max(i for i, l in enumerate(lines) if l.strip().startswith("url:")) + 1
            lines = lines[:e] + new_src + lines[e:]
        changed += 1
        if not dry:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
    print(("[dry-run] " if dry else "") + f"дополнено событий: {changed} из {len(data)}" + (f"; нет файла: {', '.join(missing)}" if missing else ""))
    for c in conflicts:
        print("  ! расхождение:", c)


if __name__ == "__main__":
    main()
