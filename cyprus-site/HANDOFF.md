# City Compas: что где лежит и как продолжить

Памятка на случай, если этот чат с Claude недоступен. Новому Claude (или разработчику) достаточно дать
этот репозиторий и попросить прочитать `HANDOFF.md`, `README.md` и `DECISIONS.md`.

## Где что хранится

| Что | Где | Чьё |
|---|---|---|
| Код сайта, генератор, все события, решения | GitHub `deniskir48-ui/sandbox`, папка `cyprus-site/`, ветка `ccr-0513f59b-8n490q` (пока не слита в `main`) | твой аккаунт GitHub |
| Живой сайт citycompas.com | Cloudflare → Workers & Pages → проект `citycompas` | твой аккаунт Cloudflare |
| Домен citycompas.com | Cloudflare Registrar, тот же аккаунт (куплен 19.11.2026) | твой |
| Статистика посещений | Cloudflare → Web Analytics → `citycompas.pages.dev` (считает и citycompas.com) | твой |
| Таблицы афиши недели | Google Drive: «Афиша Кипра · … · полный отбор для воскресного дайджеста» | твой |
| Превью страниц в Claude | claude.ai, раздел артефактов | твой аккаунт Claude; для сайта не нужны |

Не в GitHub (папка `cyprus-site/import/` нарочно не сохраняется): скачанные копии таблиц `.xlsx` — оригиналы лежат в Google Drive;
отчёт проверки недели `proverka-23-29-noyabrya.xlsx` — копия отправлена в чат.

## Что лежит в репозитории

- `src/content/events/*.yaml` — все события: одно событие — один файл.
- `scripts/build-site.mjs` — собирает сайт в `standalone/site/` (это и загружается в Cloudflare).
- `scripts/import-digest.py` + `scripts/week-fixes/<понедельник>.json` — импорт недели из полного отбора и правки по проверке.
- `scripts/enrich-apply.py` — подробности со страниц событий (описание, адрес, цена…).
- `scripts/og-image.cjs` — картинки-превью для соцсетей.
- `src/content/articles/*.md` — статьи; на сайт попадают только `status: published` (`scripts/build-articles.mjs`).
- `static/` — страницы, сделанные вручную (Green Points); копируются в сайт как есть при сборке.
- `standalone/citycompas-site.zip` — последняя собранная версия сайта, готовая к загрузке.
- `DECISIONS.md` — все решения по проекту с причинами (DEC-W01…); `README.md` — команды; `research/` — UX-исследование.

## Как обновить афишу на неделю

Нужны Node.js 20+, Python 3 с `openpyxl` и `pyyaml`, Playwright (для картинок-превью).

1. Скачать из Drive таблицу полного отбора недели как `.xlsx` в `cyprus-site/import/`.
2. Сверить события со страницами, записать решения в `scripts/week-fixes/<понедельник>.json` (образец — `2026-11-23.json`).
3. `python3 scripts/import-digest.py import/<таблица>.xlsx scripts/week-fixes/<понедельник>.json`
4. Подробности со страниц: собрать JSON и `python3 scripts/enrich-apply.py <файл>.json` (необязательно).
5. `node scripts/build-site.mjs`
6. `cd standalone/site && zip -qr ../citycompas-site.zip .`
7. Cloudflare → проект `citycompas` → Create deployment → загрузить `citycompas-site.zip`.

## Чтобы ничего не потерять

- Слить ветку `ccr-0513f59b-8n490q` в `main` на GitHub (через pull request).
- Время от времени скачивать репозиторий целиком: GitHub → Code → Download ZIP.
- Хранить доступы к GitHub, Cloudflare и Google Drive — сайт, домен и данные живут там, а не в Claude.
