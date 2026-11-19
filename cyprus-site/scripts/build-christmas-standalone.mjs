#!/usr/bin/env node
/**
 * Отдельная страница «Рождество на Кипре» — одним файлом, без остального сайта (DEC-W38).
 *   node scripts/build-christmas-standalone.mjs        → standalone/christmas.html
 * Данные — те же события Афиши с метками christmas-* (scripts/import-christmas.py), только status: published.
 *
 * Устроено так, чтобы выдержать сотни событий (дальше сюда же придёт обычная афиша):
 *  - три фильтра одной строкой каждый: «Когда» (сегодня, завтра, дни с событиями), «Где» (районы из src/data/regions.json),
 *    «Что» (виды); на телефоне строки листаются вбок;
 *  - один общий список без заголовков: сначала ближайшее; то, что уже идёт (парки, выставки), стоит как «сегодня»;
 *    при выборе дня — однодневные события этого дня и всё долгое, что в этот день открыто;
 *  - видно несколько рядов, дальше — кнопка «Показать ещё N».
 * Плитки одного размера: название, тип со значком, даты, город. По нажатию — карточка события (адрес #e-<id>).
 * Единственная ссылка наружу — «Открыть на карте»: «место, город, Cyprus» из src/data/map-places.json.
 * Прошедшее скрывается по дате на Кипре, статус парков считается там же.
 */
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'yaml';

const DIR = path.resolve('src/content/events');
const OUT = path.resolve('standalone/christmas.html');
const MON = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const MON_FULL = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const WD_FULL = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
// [метка, фильтр, тип на плитке, тип в карточке события]. Вся страница про Рождество — на плитке тип короткий.
const KINDS = [
  ['christmas-parks', 'Парки', 'Парк', 'Рождественский парк'],
  ['christmas-villages', 'Деревни', 'Деревня', 'Рождественская деревня'],
  ['christmas-lights', 'Ёлки и огни', 'Ёлка и огни', 'Ёлка и огни'],
  ['christmas-markets', 'Ярмарки', 'Ярмарка', 'Ярмарка'],
  ['christmas-other', 'Мастер-классы и другое', 'Праздник', 'Праздник'],
];
const PLACES = JSON.parse(fs.readFileSync(path.resolve('src/data/map-places.json'), 'utf8'));
const REG = JSON.parse(fs.readFileSync(path.resolve('src/data/regions.json'), 'utf8'));

const esc = (s = '') => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const day = (iso) => new Date(iso + 'T12:00:00Z');
const short = (iso) => `${day(iso).getUTCDate()} ${MON[day(iso).getUTCMonth()]}`;
const full = (iso) => `${day(iso).getUTCDate()} ${MON_FULL[day(iso).getUTCMonth()]}`;

// Ссылка на карту только по Кипру: известное место — «место, город, Cyprus», иначе — город или деревня.
// Города нет в словаре (например, «Несколько городов») — кнопки нет.
const noMap = [];
const mapUrl = (e) => {
  const city = PLACES.cities[e.city];
  if (!city) { noMap.push(e.city); return null; }
  const q = [PLACES.venues[e.venue ?? ''], city, 'Cyprus'].filter(Boolean).join(', ');
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
};

// Районы для фильтра «Где» — те же правила, что regionsOf() в src/data/regions.ts (деревни сводятся к районам).
// «Несколько городов» — берём районы из поля «место» («Никосия, Лимассол, Пафос · …»).
const regionsOf = (place) => {
  if (!place) return [];
  if (REG.places[place]) return [REG.places[place]];
  const out = new Set();
  for (const part of place.split(/\s*(?:[,;/]|\sи\s)\s*/)) if (REG.places[part] && REG.places[part] !== REG.unknown) out.add(REG.places[part]);
  for (const [kw, r] of REG.keywords) if (place.toLowerCase().includes(kw)) out.add(r);
  return [...out];
};
const regionsOfEvent = (e) => {
  const own = regionsOf(e.city).filter((r) => r !== REG.unknown);
  return own.length ? own : regionsOf(e.venue).filter((r) => r !== REG.unknown);
};

const events = fs.readdirSync(DIR).filter((f) => f.endsWith('.yaml'))
  .map((f) => ({ id: 'e-' + f.replace(/\.yaml$/, ''), ...parse(fs.readFileSync(path.join(DIR, f), 'utf8')) }))
  .filter((e) => e.status === 'published' && (e.tags ?? []).includes('christmas'));
const key = (e) => `${e.date}T${e.time ?? '00:00'}`;
const list = events.sort((a, b) => key(a).localeCompare(key(b)));
const kindOf = (e) => KINDS.find(([t]) => e.tags.includes(t)) ?? KINDS[4];
// Тип на плитке: вид из фильтра, а для «Мастер-классы и другое» — тип события из Афиши.
const OTHER_TYPES = { workshop: 'Мастер-класс', concert: 'Концерт', kids: 'Детям', theatre: 'Театр и шоу' };
const typeOf = (e, i = 2) => (kindOf(e)[0] === 'christmas-other' ? OTHER_TYPES[e.type] ?? 'Праздник' : kindOf(e)[i]);
// Значки типов — свои, линейные, 24×24; цвет берут от текста.
const ICONS = {
  park: '<circle cx="12" cy="9.5" r="6.5"/><circle cx="12" cy="9.5" r="1.2"/><path d="M12 3v5.3M12 10.7V16M5.5 9.5h5.3M13.2 9.5h5.3M10.8 15.9 8.5 21M13.2 15.9l2.3 5.1M6.5 21h11"/>',
  village: '<path d="M3.5 11 12 4l8.5 7M5.5 9.5V20h13V9.5M10 20v-5h4v5M15.5 6.9V4.5H18V9"/>',
  tree: '<path d="M12 3 7.5 9H10l-4 5.5h3.5L5 20h14l-4.5-5.5H18L14 9h2.5zM12 20v2"/>',
  market: '<path d="M4.5 4h15l2 5h-19zM9.5 4 9 9M14.5 4l.5 5M5 9v11M19 9v11M3 20h18M5 14h14"/>',
  workshop: '<circle cx="6.5" cy="17.5" r="3"/><circle cx="17.5" cy="17.5" r="3"/><path d="M8.6 15.4 17 3.5M15.4 15.4 7 3.5"/>',
  concert: '<circle cx="7.5" cy="17.5" r="3"/><path d="M10.5 17.5V4l7.5 3.5"/>',
  kids: '<path d="M12 16c-3.5 0-6-3.4-6-7a6 6 0 0 1 12 0c0 3.6-2.5 7-6 7zM11 17.5h2L12 16zM12 17.5c-1.5 1.5 1.5 2.5 0 4.5"/>',
  holiday: '<rect x="4" y="10.5" width="16" height="9.5" rx="1"/><rect x="3" y="7" width="18" height="3.5" rx="1"/><path d="M12 7v13M12 7c-1.2-3.2-5.5-3.6-4.8-.6M12 7c1.2-3.2 5.5-3.6 4.8-.6"/>',
};
const KIND_ICON = { 'christmas-parks': 'park', 'christmas-villages': 'village', 'christmas-lights': 'tree', 'christmas-markets': 'market', 'christmas-other': 'workshop' };
const iconOf = (e) => (kindOf(e)[0] === 'christmas-other' ? (ICONS[e.type] ? e.type : 'holiday') : KIND_ICON[kindOf(e)[0]]);
const svg = (k) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[k]}</svg>`;
const kinds = KINDS.map(([t, label]) => ({ t, label, n: list.filter((e) => kindOf(e)[0] === t).length })).filter((k) => k.n);

// Районы для фильтра: где есть события, по их числу; порядок при равенстве — как в regions.json.
const regCount = new Map();
for (const e of list) for (const r of regionsOfEvent(e)) regCount.set(r, (regCount.get(r) ?? 0) + 1);
const regions = [...regCount.keys()].sort((a, b) => regCount.get(b) - regCount.get(a) || REG.regions.indexOf(a) - REG.regions.indexOf(b));
const unplaced = list.filter((e) => !regionsOfEvent(e).length).map((e) => e.city);

// Даты на плитке: «сб, 21 ноя», «20–22 ноя», «20 ноя – 17 янв».
const dateShort = (e) => {
  const end = e.end_date ?? e.date;
  if (end === e.date) return `${WD[day(e.date).getUTCDay()]}, ${short(e.date)}`;
  const sameMonth = day(e.date).getUTCMonth() === day(end).getUTCMonth();
  return sameMonth ? `${day(e.date).getUTCDate()}–${short(end)}` : `${short(e.date)} – ${short(end)}`;
};
const whenFull = (e) => {
  const end = e.end_date ?? e.date;
  if (end !== e.date) return `${full(e.date)} — ${full(end)}`;
  return `${full(e.date)}, ${WD_FULL[day(e.date).getUTCDay()]}${e.time ? `, ${e.time}` : ''}`;
};

const isLong = (e) => !!e.end_date && e.end_date !== e.date;

const card = (e) => `
      <li data-kind="${kindOf(e)[0]}" data-start="${e.date}" data-end="${e.end_date ?? e.date}" data-time="${e.time ?? ''}" data-reg="${esc(regionsOfEvent(e).join('|'))}"${isLong(e) ? ' data-long="1"' : ''}${e.open_days?.length ? ` data-days="${e.open_days.join(' ')}"` : ''}>
        <a class="ev" href="#${e.id}" data-id="${e.id}">
          <span class="ev-title">${esc(e.title)}</span>
          <span class="ev-meta">
            <span class="ev-type">${svg(iconOf(e))}${esc(typeOf(e))}</span>
            <span class="ev-date">${esc(dateShort(e))}</span>
            <span class="ev-city">${esc(e.city)}</span>
          </span>
        </a>
      </li>`;

// Данные для карточки события — только публичные поля.
const detail = Object.fromEntries(list.map((e) => [e.id, {
  kind: typeOf(e, 3), icon: iconOf(e), group: kindOf(e)[0], title: e.title, when: whenFull(e), place: `${e.city}${e.venue ? ` · ${e.venue}` : ''}`,
  summary: e.summary ?? '', hours: e.hours ?? '', price: e.price ?? '', map: mapUrl(e),
  start: e.date, end: e.end_date ?? e.date, park: e.tags.includes('christmas-parks'),
}]));

const LOGO = 'M4.00 16.38 L5.34 17.01 L6.17 16.25 L7.10 15.49 L8.45 15.24 L9.90 15.75 L10.83 15.10 L10.83 13.27 L12.58 13.59 L14.85 13.80 L17.22 13.59 L19.80 13.16 L22.38 12.52 L24.96 11.23 L27.95 9.94 L26.51 11.02 L23.92 12.31 L21.55 13.91 L21.24 15.86 L22.69 17.79 L21.65 17.69 L19.28 17.79 L18.15 18.33 L17.84 19.40 L15.88 20.37 L13.09 20.69 L11.85 21.34 L11.02 22.20 L10.30 21.12 L8.45 21.12 L5.86 20.26 L5.03 19.08 L4.41 17.90 Z';

const html = `<title>Рождество на Кипре</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Рождественские парки Кипра и праздники ближайших дней: ёлки, деревни, ярмарки.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Unbounded:wght@600;700;800&display=swap">
<style>
  /* Вечерний Кипр в декабре: ночное небо, гирлянда, голубой и оранжевый «Гида по Кипру». Сознательно одна тёмная тема.
     Раскладка: заголовок → три строки фильтров → один список плиток; карточка события открывается поверх списка. */
  :root {
    color-scheme: dark;
    --night: #0a1120; --card: #111a2e; --card-hi: #16223b; --line: #22304d; --text: #eef3f9; --muted: #9fb0c8;
    --sky: #9fd5f2; --sun: #f26b21; --warm: #ffd38a; --ok: #7ee2b8;
    --gutter: max(16px, env(safe-area-inset-left, 0px));
    --display: "Unbounded", "Onest", system-ui, sans-serif; --body: "Onest", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  html { background: var(--night); }
  body { background: var(--night); color: var(--text); font-family: var(--body); font-size: 16px; line-height: 1.5;
    padding-left: var(--gutter); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 40px; }
  body.locked { overflow: hidden; }
  .wrap { max-width: 1040px; margin: 0 auto; }
  .garland { display: block; width: 100%; height: 50px; }
  .bulb { animation: tw 3.2s ease-in-out infinite; } .bulb:nth-child(3n) { animation-delay: .8s; } .bulb:nth-child(3n+1) { animation-delay: 1.7s; }
  @keyframes tw { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
  @media (prefers-reduced-motion: reduce) { .bulb { animation: none; } }
  header { padding-block: 6px 20px; }
  .kicker { font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--sky); margin: 0; }
  h1 { font-family: var(--display); font-weight: 800; font-size: clamp(2rem, 7.5vw, 3.4rem); line-height: 1.06; margin: 10px 0 0; text-wrap: balance; }
  h1 em { font-style: normal; color: var(--warm); }

  /* У каждого вида свой цвет: парки — оранжевый, деревни — голубой, ёлки — зелёный, ярмарки — жёлтый, остальное — сиреневый. */
  [data-kind="christmas-parks"] { --c: #ffa463; } [data-kind="christmas-villages"] { --c: #8fd0f5; } [data-kind="christmas-lights"] { --c: #6fe3a5; }
  [data-kind="christmas-markets"] { --c: #ffd166; } [data-kind="christmas-other"] { --c: #c4b0ff; }

  /* Фильтры: три строки — когда, где, что. На телефоне каждая строка листается вбок, на компьютере переносится. */
  .filters { display: grid; gap: 8px; }
  .row { display: flex; gap: 8px; overflow-x: auto; margin-inline: calc(-1 * var(--gutter)); padding: 3px var(--gutter); scrollbar-width: none; }
  .row::-webkit-scrollbar { display: none; }
  @media (min-width: 700px) { .row { flex-wrap: wrap; overflow: visible; margin-inline: 0; padding-inline: 0; } }
  .chip { flex: none; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; font: 600 .9rem var(--body); color: var(--text); background: transparent; border: 1px solid var(--line); border-radius: 999px; padding: 8px 14px; cursor: pointer; }
  .chip[hidden] { display: none; }
  .chip .ic { color: var(--c); }
  .chip[aria-pressed="true"] { background: var(--c, var(--text)); border-color: var(--c, var(--text)); color: #0a1120; }
  .chip[aria-pressed="true"] .ic { color: inherit; }

  #list { margin-top: 20px; }
  .more { display: block; width: 100%; max-width: 340px; margin: 14px auto 0; padding: 11px 16px; border-radius: 999px; border: 1px solid var(--line); background: transparent; color: var(--text); font: 600 .92rem var(--body); cursor: pointer; }
  .more[hidden] { display: none; }
  .more:hover { border-color: #3a4d74; background: var(--card); }
  .empty { margin: 12px 0 0; color: var(--muted); }
  .empty button { font: 600 1rem var(--body); color: var(--sky); background: none; border: 0; padding: 0; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }

  /* Плитки одного размера: название (до 3 строк), под ним тип, даты, город. 2 в ряд на телефоне, 3–4 на компьютере. */
  .evs { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-auto-rows: 1fr; }
  @media (min-width: 640px) { .evs { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; } }
  @media (min-width: 900px) { .evs { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
  .evs > li { display: flex; }
  .evs > li[hidden] { display: none; }
  .ev { box-sizing: border-box; flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 13px 12px 12px; background: color-mix(in srgb, var(--c) 13%, var(--night)); border: 1px solid color-mix(in srgb, var(--c) 42%, var(--night)); border-radius: 16px; color: inherit; text-decoration: none; transition: border-color .15s, background .15s; }
  @media (min-width: 640px) { .ev { padding: 15px 14px 14px; } }
  .ev:hover { border-color: var(--c); background: color-mix(in srgb, var(--c) 20%, var(--night)); }
  .ev-title { flex: 1; font-weight: 650; font-size: .95rem; line-height: 1.3; overflow-wrap: anywhere; hyphens: auto; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  @media (min-width: 640px) { .ev-title { font-size: 1rem; } }
  .ev-meta { display: grid; gap: 3px; min-width: 0; }
  .ev-meta > span { overflow-wrap: anywhere; }
  .ic { flex: none; width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
  .ev-type { display: flex; align-items: center; gap: 6px; font-size: .82rem; font-weight: 700; color: var(--c); }
  .ev-type .ic { width: 20px; height: 20px; }
  .ev-date { font-size: .88rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .ev-city { font-size: .86rem; color: var(--muted); }
  .ev:focus-visible, .chip:focus-visible, .more:focus-visible, .empty button:focus-visible, .sheet button:focus-visible, .sheet a:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }

  /* Карточка события */
  .shade[hidden] { display: none; }
  .shade { position: fixed; inset: 0; z-index: 20; background: rgba(4, 8, 16, .66); display: flex; align-items: flex-end; justify-content: center; }
  .sheet { position: relative; width: 100%; max-width: 620px; max-height: calc(100% - 40px); overflow: auto; background: var(--card); border: 1px solid var(--line);
    border-radius: 22px 22px 0 0; padding: 22px max(20px, env(safe-area-inset-right, 0px)) calc(24px + env(safe-area-inset-bottom, 0px)) max(20px, env(safe-area-inset-left, 0px)); display: grid; gap: 12px; }
  @media (min-width: 700px) { .shade { align-items: center; } .sheet { border-radius: 22px; padding: 26px 28px; } }
  .close { position: absolute; top: 12px; right: 12px; width: 38px; height: 38px; border-radius: 999px; border: 1px solid var(--line); background: var(--night); color: var(--text); font-size: 1.3rem; line-height: 1; cursor: pointer; }
  .s-kind { display: flex; align-items: center; gap: 8px; font-size: .76rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--c, var(--sky)); padding-right: 44px; }
  .sheet h2 { font-family: var(--display); font-weight: 700; font-size: 1.35rem; line-height: 1.2; margin: 0; padding-right: 36px; text-wrap: balance; }
  .s-status { justify-self: start; font-size: .8rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: color-mix(in srgb, var(--sun) 20%, transparent); color: #ffb488; }
  .s-status.now { background: color-mix(in srgb, var(--ok) 16%, transparent); color: var(--ok); }
  .s-facts { margin: 0; display: grid; gap: 8px; }
  .s-facts div { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 10px; }
  .s-facts dt { color: var(--muted); font-size: .9rem; } .s-facts dd { margin: 0; }
  .s-summary { margin: 0; color: #d6e0ec; }
  .s-map { justify-self: start; display: inline-flex; align-items: center; gap: 8px; margin-top: 4px; padding: 11px 18px; border-radius: 999px; background: var(--warm); color: #1c1300; font-weight: 700; text-decoration: none; }

  footer { margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: .9rem; display: grid; gap: 8px; }
  .brand { display: inline-flex; align-items: center; gap: 8px; font-family: var(--display); font-weight: 600; color: var(--text); }
</style>

<div class="wrap" lang="ru">
  <svg class="garland" viewBox="0 0 800 50" preserveAspectRatio="none" aria-hidden="true">
    <path d="M0 8 Q100 42 200 14 T400 14 T600 14 T800 8" fill="none" stroke="#2a3a5c" stroke-width="2"/>
    ${[[40, 19, '#ffd38a'], [95, 28, '#9fd5f2'], [150, 26, '#f26b21'], [205, 15, '#ffd38a'], [260, 21, '#7ee2b8'], [315, 28, '#9fd5f2'], [365, 21, '#f26b21'], [415, 14, '#ffd38a'], [470, 22, '#9fd5f2'], [520, 28, '#7ee2b8'], [570, 21, '#f26b21'], [620, 14, '#ffd38a'], [675, 22, '#9fd5f2'], [725, 27, '#f26b21'], [775, 15, '#ffd38a']]
      .map(([x, y, c]) => `<circle class="bulb" cx="${x}" cy="${y}" r="4.5" fill="${c}"/>`).join('')}
  </svg>
  <header>
    <p class="kicker">Сезон 2026–2027</p>
    <h1>Рождество <em>на&nbsp;Кипре</em></h1>
  </header>

  <div class="filters">
    <div class="row" id="f-date" role="group" aria-label="Когда">
      <button type="button" class="chip" data-v="" aria-pressed="true">Все даты</button>
    </div>
    <div class="row" id="f-reg" role="group" aria-label="Где">
      <button type="button" class="chip" data-v="" aria-pressed="true">Весь Кипр</button>
      ${regions.map((r) => `<button type="button" class="chip" data-v="${esc(r)}" aria-pressed="false">${esc(r)}</button>`).join('\n      ')}
    </div>
    <div class="row" id="f-kind" role="group" aria-label="Что">
      <button type="button" class="chip" data-v="" aria-pressed="true">Все события</button>
      ${kinds.map((k) => `<button type="button" class="chip" data-v="${k.t}" data-kind="${k.t}" aria-pressed="false">${svg(KIND_ICON[k.t])}${k.label}</button>`).join('\n      ')}
    </div>
  </div>

  <div id="list">
    <ul class="evs" id="evs">${list.map(card).join('')}
    </ul>
    <button type="button" class="more" id="more" hidden></button>
    <p class="empty" id="empty" hidden>Ничего не нашлось. <button type="button" id="reset">Сбросить фильтры</button></p>
  </div>

  <footer>
    <span class="brand"><svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#9fd5f2"/><circle cx="23" cy="8.5" r="3.6" fill="#f26b21"/><path transform="translate(0 3)" d="${LOGO}" fill="#0e1116"/></svg>Гид по Кипру</span>
    <span>Время, цены и программа могут меняться — перед поездкой уточняйте у организаторов.</span>
  </footer>
</div>

<div class="shade" id="shade" hidden>
  <div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="s-title">
    <button type="button" class="close" id="s-close" aria-label="Закрыть">×</button>
    <span class="s-kind" id="s-kind"></span>
    <h2 id="s-title"></h2>
    <span class="s-status" id="s-status" hidden></span>
    <dl class="s-facts" id="s-facts"></dl>
    <p class="s-summary" id="s-summary"></p>
    <a class="s-map" id="s-map" href="#" target="_blank" rel="noopener">Открыть на карте ↗</a>
  </div>
</div>

<script>
  (function () {
    var DATA = ${JSON.stringify(detail)};
    var MON = ${JSON.stringify(MON_FULL)}, MON_S = ${JSON.stringify(MON)}, WD = ${JSON.stringify(WD)};
    var ICONS = ${JSON.stringify(Object.fromEntries(Object.keys(ICONS).map((k) => [k, svg(k)])))};
    var DAYS = ['в воскресенье', 'в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу'];
    var today;
    try { today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Nicosia' }).format(new Date()); } catch (e) { today = new Date().toISOString().slice(0, 10); }
    var d = function (iso) { return new Date(iso + 'T12:00:00Z'); };
    var plus = function (iso, n) { return new Date(d(iso).getTime() + n * 86400000).toISOString().slice(0, 10); };
    var human = function (iso) { return d(iso).getUTCDate() + ' ' + MON[d(iso).getUTCMonth()]; };
    var all = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
    var el = function (id) { return document.getElementById(id); };
    var tomorrow = plus(today, 1);

    // Статус парка в карточке события: работает до… / откроется…
    var status = function (x) {
      if (!x.park || x.end < today) return null;
      if (x.start > today) {
        var n = Math.round((d(x.start) - d(today)) / 86400000);
        return { text: n === 1 ? 'Откроется завтра' : n < 7 ? 'Откроется ' + DAYS[d(x.start).getUTCDay()] : 'Откроется ' + human(x.start), now: false };
      }
      return { text: x.end === today ? 'Сегодня последний день' : 'Работает до ' + human(x.end), now: true };
    };

    // Прошедшее убираем.
    all('#evs > li').forEach(function (li) { if (li.dataset.end < today) li.remove(); });
    var items = all('#evs > li'), list = el('evs');

    // «Когда»: сегодня, завтра и дальше дни, в которые есть однодневные события.
    var dates = {}; dates[today] = 1; dates[tomorrow] = 1;
    items.forEach(function (li) { if (!li.dataset.long) dates[li.dataset.start] = 1; });
    var dateRow = el('f-date');
    Object.keys(dates).sort().forEach(function (iso) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'chip'; b.dataset.v = iso; b.setAttribute('aria-pressed', 'false');
      b.textContent = iso === today ? 'Сегодня' : iso === tomorrow ? 'Завтра' : WD[d(iso).getUTCDay()] + ', ' + d(iso).getUTCDate() + ' ' + MON_S[d(iso).getUTCMonth()];
      dateRow.appendChild(b);
    });

    var state = { date: '', reg: '', kind: '' }, shown = 0;
    var match = function (li, s) {
      if (s.kind && li.dataset.kind !== s.kind) return false;
      if (s.reg && li.dataset.reg.split('|').indexOf(s.reg) < 0) return false;
      // Долгое событие — если в этот день открыто (у деревень — только дни из open_days).
      if (s.date) return li.dataset.long ? (li.dataset.days ? li.dataset.days.split(' ').indexOf(s.date) >= 0 : li.dataset.start <= s.date && s.date <= li.dataset.end) : li.dataset.start === s.date;
      return true;
    };
    // Районы и виды без событий (после того как прошедшее убрано) не показываем.
    all('#f-reg .chip[data-v], #f-kind .chip[data-v]').forEach(function (c) {
      if (!c.dataset.v) return;
      var probe = { date: '', reg: '', kind: '' }; probe[c.parentNode.id === 'f-reg' ? 'reg' : 'kind'] = c.dataset.v;
      c.hidden = !items.some(function (li) { return match(li, probe); });
    });

    // Все плитки одной высоты: по самой высокой видимой.
    var equalize = function () {
      var tiles = all('#list .ev');
      tiles.forEach(function (t) { t.style.minHeight = ''; });
      var h = 0;
      tiles.forEach(function (t) { if (t.offsetParent) h = Math.max(h, t.getBoundingClientRect().height); });
      if (h) tiles.forEach(function (t) { t.style.minHeight = Math.ceil(h) + 'px'; });
    };
    // Порядок: сначала ближайшее. Уже идущее (парк открыт с 13-го) стоит как «сегодня» или как выбранный день;
    // в один день — сначала однодневные по времени, потом долгие.
    var sortKey = function (li) {
      var from = state.date || today, eff = li.dataset.start < from ? from : li.dataset.start;
      // Открыто не каждый день — по ближайшему дню работы.
      if (li.dataset.days) eff = li.dataset.days.split(' ').filter(function (x) { return x >= from; })[0] || li.dataset.end;
      return eff + (li.dataset.long ? '1' : '0') + (li.dataset.time || '00:00') + li.dataset.start;
    };
    // Сколько плиток видно до «Показать ещё»: 6 рядов на телефоне, 4 на компьютере; кнопка добавляет столько же.
    var page = function () { return matchMedia('(min-width: 900px)').matches ? 16 : 12; };
    function render(keep) {
      items.sort(function (a, b) { var x = sortKey(a), y = sortKey(b); return x < y ? -1 : x > y ? 1 : 0; });
      items.forEach(function (li) { list.appendChild(li); });
      var vis = items.filter(function (li) { return match(li, state); });
      if (!keep) shown = page();
      // Под кнопкой осталось бы 1–2 плитки — показываем всё.
      var limit = vis.length - shown <= 2 ? vis.length : shown;
      items.forEach(function (li) { li.hidden = true; });
      vis.forEach(function (li, i) { li.hidden = i >= limit; });
      var rest = vis.length - limit, more = el('more');
      more.hidden = rest <= 0; if (rest > 0) more.textContent = 'Показать ещё ' + Math.min(rest, page());
      el('empty').hidden = vis.length > 0;
      equalize();
    }
    all('.filters .row').forEach(function (row) {
      var keyName = { 'f-date': 'date', 'f-reg': 'reg', 'f-kind': 'kind' }[row.id];
      row.addEventListener('click', function (e) {
        var c = e.target.closest('.chip'); if (!c) return;
        all('.chip', row).forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
        state[keyName] = c.dataset.v; render();
      });
    });
    el('more').addEventListener('click', function () { shown += page(); render(true); });
    el('reset').addEventListener('click', function () {
      state = { date: '', reg: '', kind: '' };
      all('.filters .row').forEach(function (row) { all('.chip', row).forEach(function (x, i) { x.setAttribute('aria-pressed', String(i === 0)); }); });
      render();
    });
    render();
    var raf = 0;
    window.addEventListener('resize', function () { cancelAnimationFrame(raf); raf = requestAnimationFrame(equalize); });
    // Шрифты приходят позже первого расчёта — пересчитываем, когда они загрузятся.
    if (document.fonts) { document.fonts.addEventListener('loadingdone', equalize); if (document.fonts.ready) document.fonts.ready.then(equalize); }
    window.addEventListener('load', equalize);

    // Карточка события: открывается по адресу #e-<id>, закрывается крестиком, фоном или Esc.
    var shade = el('shade'), last = null;
    function fact(dt, dd) { return dd ? '<div><dt>' + dt + '</dt><dd></dd></div>' : ''; }
    function show() {
      var id = location.hash.slice(1), x = DATA[id];
      if (!x) { shade.hidden = true; document.body.classList.remove('locked'); if (last) { last.focus(); last = null; } return; }
      el('sheet').dataset.kind = x.group; el('s-kind').innerHTML = ICONS[x.icon]; el('s-kind').appendChild(document.createTextNode(x.kind));
      el('s-title').textContent = x.title;
      var st = status(x), s = el('s-status');
      s.hidden = !st; if (st) { s.textContent = st.text; s.classList.toggle('now', st.now); }
      var f = el('s-facts'); f.innerHTML = fact('Когда', x.when) + fact('Где', x.place) + fact('Часы', x.hours) + fact('Стоимость', x.price);
      var vals = [x.when, x.place, x.hours, x.price].filter(Boolean);
      Array.prototype.forEach.call(f.querySelectorAll('dd'), function (dd, i) { dd.textContent = vals[i]; });
      el('s-summary').textContent = x.summary; el('s-summary').hidden = !x.summary;
      var m = el('s-map'); m.hidden = !x.map; if (x.map) m.href = x.map;
      shade.hidden = false; document.body.classList.add('locked'); el('s-close').focus();
    }
    function close() {
      if (history.length > 1 && last) history.back(); else { location.hash = ''; }
    }
    el('list').addEventListener('click', function (e) { var a = e.target.closest('.ev'); if (a) last = a; });
    el('s-close').addEventListener('click', close);
    shade.addEventListener('click', function (e) { if (e.target === shade) close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !shade.hidden) close(); });
    window.addEventListener('hashchange', show);
    show();
  })();
</script>
`;

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, html);
console.log(`standalone/christmas.html: ${list.length} событий (${kinds.map((k) => `${k.label} ${k.n}`).join(', ')}); районы: ${regions.map((r) => `${r} ${regCount.get(r)}`).join(', ')}`);
if (unplaced.length) console.log(`без района (места нет в regions.json): ${[...new Set(unplaced)].join(', ')}`);
if (noMap.length) console.log(`без карты (города нет в map-places.json): ${[...new Set(noMap)].join(', ')}`);
