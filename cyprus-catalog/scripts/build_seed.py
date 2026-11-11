"""Build catalog seed CSV from the exported 'Коллаборации — контакты и ответы' workbook.

Usage: python3 build_seed.py <collab.xlsx> <out.csv>
Only public business data goes to the catalog. Partner statuses go to a separate
internal file (partners_internal.csv), never to the public site.
"""
import csv, re, sys, openpyxl

FREE_MAIL = ("gmail.", "hotmail.", "yahoo.", "outlook.", "mail.ru", "yandex.")
CAT_MAP = {
    "Лодки": ("leisure", "boats"), "Прокат лодок": ("leisure", "boats"),
    "Отдельная баня": ("leisure", "spa-banya"), "Отдельная сауна": ("leisure", "spa-banya"),
    "Отдельный хаммам": ("leisure", "spa-banya"), "Отель / SPA": ("leisure", "spa-hotels"),
    "Греческий язык / A2–B1": ("education", "greek"),
    "Авто / импорт из Японии": ("cars", "japan-import"),
    "События / Билеты": ("events", "ticketing"), "События / билеты": ("events", "ticketing"),
    "События / Афиша": ("events", "event-guides"),
    "Стоматология": ("health", "dentistry"),
}
FIELDS = ["slug", "name", "section", "category", "city", "website", "website_source",
          "public_contact", "short_description", "languages", "listing_type",
          "verified_by_author", "last_checked", "publish_ready", "source"]

def slugify(s):
    tr = str.maketrans("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", "abvgdeejziiklmnoprstufhccss_y_eua")
    s = s.lower().translate(tr)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def site_from_email(email):
    m = re.search(r"@([\w.-]+\.\w+)", email or "")
    if not m or any(f in m.group(1) for f in FREE_MAIL):
        return ""
    return "https://" + m.group(1).lower()

def is_public(email):
    return bool(email) and "@" in email and not any(f in email for f in FREE_MAIL)

wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
rows, internal, seen = [], [], set()

def add(name, cat, city="", site="", site_src="", contact="", desc="", src="", status="", note=""):
    section, category = CAT_MAP[cat] if cat in CAT_MAP else cat
    slug = slugify(name)
    if slug in seen or any(slug.startswith(x + "-") for x in seen):
        return  # duplicate, e.g. 'Ayii Anargyri Spa / Secret Forest' vs 'Ayii Anargyri Spa'
    seen.add(slug)
    rows.append(dict(slug=slug, name=name.strip(), section=section, category=category, city=city,
                     website=site, website_source=site_src, public_contact=contact,
                     short_description=desc, languages="", listing_type="basic",
                     verified_by_author="no", last_checked="", publish_ready="no", source=src))
    if status or note:
        internal.append(dict(slug=slug, name=name.strip(), status=status, note=note))

# 1) Dedicated sheets with richer data first (city + website present)
for r in wb["Бани и SPA"].iter_rows(min_row=5, values_only=True):
    if not r[0]: continue
    cat = "Отель / SPA" if "Отель" in str(r[2]) else "Отдельная баня"
    contact = r[3] if is_public(str(r[3])) else ""
    add(r[0], cat, r[1] or "", r[4] if str(r[4]).startswith("http") else "", "sheet", contact,
        r[2] or "", "Коллаборации/Бани и SPA", r[6] or "", r[7] or "")
for r in wb["Греческий — партнёры"].iter_rows(min_row=2, values_only=True):
    if not r[0]: continue
    city = (r[1] or "").split(",")[-1].strip() if "," in (r[1] or "") else ("онлайн" if "Онлайн" in (r[1] or "") or "Прилож" in (r[1] or "") else "")
    contact = r[3] if is_public(str(r[3])) else ""
    add(r[0], "Греческий язык / A2–B1", city, r[4] or "", "sheet", contact, f"{r[1]}; {r[2]}",
        "Коллаборации/Греческий — партнёры", r[6] or "", r[7] or "")
# 2) Main outreach sheet
for r in wb["Переписки"].iter_rows(min_row=5, values_only=True):
    if not r[0] or r[1] not in CAT_MAP: continue
    name = r[0].replace("Ichiro Fukuda / ", "")
    email = str(r[2] or "")
    site = site_from_email(email)
    add(name, r[1], "", site, "domain_from_email" if site else "", email if is_public(email) else "",
        "", "Коллаборации/Переписки", str(r[5] or ""), str(r[6] or "")[:300])

# 3) Real estate + related from the doc 'Черновики коллабораций' (03.11.2026), not contacted yet
RE_DOC = "Doc: Черновики коллабораций — недвижимость (03.11)"
for name, site, cat in [
    ("DOM Real Estate", "https://dom.com.cy", "agencies"),
    ("D. Zavos Group", "https://zavos.com", "developers"),
    ("bbf", "https://bbf.com", "developers"),
    ("Imperio Properties", "https://www.imperioproperties.com", "developers"),
    ("Leptos Estates", "https://www.leptosestates.com", "developers"),
    ("Pafilia", "https://www.pafilia.com", "developers"),
    ("Cybarco", "https://www.cybarco.com", "developers"),
    ("Aristo Developers", "https://www.aristodevelopers.com", "developers"),
    ("Cyprus Property Gallery", "https://cypruspropertygallery.com", "agencies"),
    ("Cyprus VIP Estates", "https://cyprusvipestates.com", "agencies"),
    ("Bank of Cyprus — ипотека", "https://www.bankofcyprus.com/en-gb/Personal/loans/Housing/", "mortgage"),
    ("Eurobank Cyprus — ипотека", "https://www.eurobank.cy/en/personal/housing/home-loan", "mortgage"),
    ("Anymaster", "https://anymaster.com", "home-services"),
]:
    add(name, ("real-estate", cat), "", site, "doc", "", "", RE_DOC, "не писали (на 03.11)", "")
# Cars from drafts doc (no website in doc)
for name in ["SunCars", "FreshCar"]:
    add(name, ("cars", "dealers-used"), "", "", "", "", "", "Doc: Черновики коллабораций — авто (03.11)", "черновик, не отправлено", "")

with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
with open(sys.argv[2].replace("companies_seed", "partners_internal"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, ["slug", "name", "status", "note"]); w.writeheader(); w.writerows(internal)
from collections import Counter
print(len(rows), Counter((r["section"], r["category"]) for r in rows))
print("with website:", sum(1 for r in rows if r["website"]), "with city:", sum(1 for r in rows if r["city"]))
