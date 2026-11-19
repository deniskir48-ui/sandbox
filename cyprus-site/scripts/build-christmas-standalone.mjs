#!/usr/bin/env node
/**
 * Отдельная страница «Рождество на Кипре» — одним файлом, без остального сайта (DEC-W38).
 *   node scripts/build-christmas-standalone.mjs        → standalone/christmas.html
 * Данные — те же события Афиши с метками christmas-* (scripts/import-christmas.py), только status: published.
 * Список — плитки одного размера (2 в ряд на телефоне, 3–4 на компьютере): название, тип, даты, город.
 * По нажатию открывается карточка события
 * (адрес #e-<id>, его можно отправить). Единственная ссылка наружу — «Открыть на карте»: запрос по-английски
 * «место, город, Cyprus» из src/data/map-places.json, иначе Google находит одноимённые места в Испании и Греции.
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

const events = fs.readdirSync(DIR).filter((f) => f.endsWith('.yaml'))
  .map((f) => ({ id: 'e-' + f.replace(/\.yaml$/, ''), ...parse(fs.readFileSync(path.join(DIR, f), 'utf8')) }))
  .filter((e) => e.status === 'published' && (e.tags ?? []).includes('christmas'));
const key = (e) => `${e.date}T${e.time ?? '00:00'}`;
const list = events.sort((a, b) => key(a).localeCompare(key(b)));
const kindOf = (e) => KINDS.find(([t]) => e.tags.includes(t)) ?? KINDS[4];
// Тип на плитке: вид из фильтра, а для «Мастер-классы и другое» — тип события из Афиши.
const OTHER_TYPES = { workshop: 'Мастер-класс', concert: 'Концерт', kids: 'Детям', theatre: 'Театр и шоу' };
const typeOf = (e, i = 2) => (kindOf(e)[0] === 'christmas-other' ? OTHER_TYPES[e.type] ?? 'Праздник' : kindOf(e)[i]);
const kinds = KINDS.map(([t, label]) => ({ t, label, n: list.filter((e) => kindOf(e)[0] === t).length })).filter((k) => k.n);

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

const card = (e) => {
  const park = e.tags.includes('christmas-parks');
  return `
    <li data-kind="${kindOf(e)[0]}" data-end="${e.end_date ?? e.date}">
      <a class="ev${park ? ' is-park' : ''}" href="#${e.id}" data-id="${e.id}">
        <span class="ev-title">${esc(e.title)}</span>
        <span class="ev-meta">
          <span class="ev-type">${esc(typeOf(e))}</span>
          <span class="ev-date">${esc(dateShort(e))}</span>
          <span class="ev-city">${esc(e.city)}</span>
        </span>
      </a>
    </li>`;
};

// Данные для карточки события — только публичные поля.
const detail = Object.fromEntries(list.map((e) => [e.id, {
  kind: typeOf(e, 3), title: e.title, when: whenFull(e), place: `${e.city}${e.venue ? ` · ${e.venue}` : ''}`,
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
     Раскладка: заголовок → фильтр → одинаковые карточки; карточка события открывается поверх списка. */
  :root {
    color-scheme: dark;
    --night: #0a1120; --card: #111a2e; --card-hi: #16223b; --line: #22304d; --text: #eef3f9; --muted: #9fb0c8;
    --sky: #9fd5f2; --sun: #f26b21; --warm: #ffd38a; --ok: #7ee2b8;
    --display: "Unbounded", "Onest", system-ui, sans-serif; --body: "Onest", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  html { background: var(--night); }
  body { background: var(--night); color: var(--text); font-family: var(--body); font-size: 16px; line-height: 1.5;
    padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 40px; }
  body.locked { overflow: hidden; }
  .wrap { max-width: 1040px; margin: 0 auto; }
  .garland { display: block; width: 100%; height: 50px; }
  .bulb { animation: tw 3.2s ease-in-out infinite; } .bulb:nth-child(3n) { animation-delay: .8s; } .bulb:nth-child(3n+1) { animation-delay: 1.7s; }
  @keyframes tw { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
  @media (prefers-reduced-motion: reduce) { .bulb { animation: none; } }
  header { padding-block: 6px 22px; }
  .kicker { font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--sky); margin: 0; }
  h1 { font-family: var(--display); font-weight: 800; font-size: clamp(2rem, 7.5vw, 3.4rem); line-height: 1.06; margin: 10px 0 0; text-wrap: balance; }
  h1 em { font-style: normal; color: var(--warm); }

  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
  .chip { font: 600 .9rem var(--body); color: var(--text); background: transparent; border: 1px solid var(--line); border-radius: 999px; padding: 8px 14px; cursor: pointer; }
  .chip em { font-style: normal; color: var(--muted); font-weight: 500; }
  .chip[aria-pressed="true"] { background: var(--sky); border-color: var(--sky); color: #0a1120; }
  .chip[aria-pressed="true"] em { color: inherit; opacity: .7; }

  /* Плитки одного размера: название (до 3 строк), под ним тип, даты, город. 2 в ряд на телефоне, 3–4 на компьютере. */
  .evs { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-auto-rows: 1fr; }
  @media (min-width: 640px) { .evs { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; } }
  @media (min-width: 900px) { .evs { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
  .evs > li { display: flex; }
  .ev { flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 13px 12px 12px; background: var(--card); border: 1px solid var(--line); border-radius: 16px; color: inherit; text-decoration: none; transition: border-color .15s, background .15s; }
  @media (min-width: 640px) { .ev { padding: 15px 14px 14px; } }
  .ev:hover { border-color: #3a4d74; background: var(--card-hi); }
  .ev-title { flex: 1; font-weight: 650; font-size: .95rem; line-height: 1.3; overflow-wrap: anywhere; hyphens: auto; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  @media (min-width: 640px) { .ev-title { font-size: 1rem; } }
  .ev-meta { display: grid; gap: 3px; min-width: 0; }
  .ev-meta > span { overflow-wrap: anywhere; }
  .ev-type { font-size: .78rem; font-weight: 700; color: var(--sky); }
  .is-park .ev-type { color: var(--warm); }
  .ev-date { font-size: .88rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .ev-city { font-size: .86rem; color: var(--muted); }
  .ev:focus-visible, .chip:focus-visible, .sheet button:focus-visible, .sheet a:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }

  /* Карточка события */
  .shade[hidden] { display: none; }
  .shade { position: fixed; inset: 0; z-index: 20; background: rgba(4, 8, 16, .66); display: flex; align-items: flex-end; justify-content: center; }
  .sheet { position: relative; width: 100%; max-width: 620px; max-height: calc(100% - 40px); overflow: auto; background: var(--card); border: 1px solid var(--line);
    border-radius: 22px 22px 0 0; padding: 22px max(20px, env(safe-area-inset-right, 0px)) calc(24px + env(safe-area-inset-bottom, 0px)) max(20px, env(safe-area-inset-left, 0px)); display: grid; gap: 12px; }
  @media (min-width: 700px) { .shade { align-items: center; } .sheet { border-radius: 22px; padding: 26px 28px; } }
  .close { position: absolute; top: 12px; right: 12px; width: 38px; height: 38px; border-radius: 999px; border: 1px solid var(--line); background: var(--night); color: var(--text); font-size: 1.3rem; line-height: 1; cursor: pointer; }
  .s-kind { font-size: .76rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--sky); padding-right: 44px; }
  .sheet h2 { font-family: var(--display); font-weight: 700; font-size: 1.35rem; line-height: 1.2; margin: 0; padding-right: 36px; text-wrap: balance; }
  .s-status { justify-self: start; font-size: .8rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: color-mix(in srgb, var(--sun) 20%, transparent); color: #ffb488; }
  .s-status.now { background: color-mix(in srgb, var(--ok) 16%, transparent); color: var(--ok); }
  .s-facts { margin: 0; display: grid; gap: 8px; }
  .s-facts div { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 10px; }
  .s-facts dt { color: var(--muted); font-size: .9rem; } .s-facts dd { margin: 0; }
  .s-summary { margin: 0; color: #d6e0ec; }
  .s-map { justify-self: start; display: inline-flex; align-items: center; gap: 8px; margin-top: 4px; padding: 11px 18px; border-radius: 999px; background: var(--warm); color: #1c1300; font-weight: 700; text-decoration: none; }

  footer { margin-top: 30px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: .9rem; display: grid; gap: 8px; }
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

  <div class="chips" role="group" aria-label="Что показать">
    <button type="button" class="chip" id="k-all" data-kind="" aria-pressed="true">Все <em>${list.length}</em></button>
    ${kinds.map((k) => `<button type="button" class="chip" id="k-${k.t}" data-kind="${k.t}" aria-pressed="false">${k.label} <em>${k.n}</em></button>`).join('\n    ')}
  </div>
  <ul class="evs" id="evs">${list.map(card).join('')}
  </ul>

  <footer>
    <span class="brand"><svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#9fd5f2"/><circle cx="23" cy="8.5" r="3.6" fill="#f26b21"/><path transform="translate(0 3)" d="${LOGO}" fill="#0e1116"/></svg>Гид по Кипру</span>
    <span>Время, цены и программа могут меняться — перед поездкой уточняйте у организаторов.</span>
  </footer>
</div>

<div class="shade" id="shade" hidden>
  <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="s-title">
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
    var MON = ${JSON.stringify(MON_FULL)};
    var DAYS = ['в воскресенье', 'в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу'];
    var today;
    try { today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Nicosia' }).format(new Date()); } catch (e) { today = new Date().toISOString().slice(0, 10); }
    var d = function (iso) { return new Date(iso + 'T12:00:00Z'); };
    var human = function (iso) { return d(iso).getUTCDate() + ' ' + MON[d(iso).getUTCMonth()]; };
    // Статус парка в карточке события: работает до… / откроется…
    var status = function (x) {
      if (!x.park || x.end < today) return null;
      if (x.start > today) {
        var n = Math.round((d(x.start) - d(today)) / 86400000);
        return { text: n === 1 ? 'Откроется завтра' : n < 7 ? 'Откроется ' + DAYS[d(x.start).getUTCDay()] : 'Откроется ' + human(x.start), now: false };
      }
      return { text: x.end === today ? 'Сегодня последний день' : 'Работает до ' + human(x.end), now: true };
    };

    // Список: прошедшее скрыто.
    Array.prototype.slice.call(document.querySelectorAll('#evs > li')).forEach(function (li) { if (li.dataset.end < today) li.remove(); });
    var live = Array.prototype.slice.call(document.querySelectorAll('#evs > li'));
    var chips = document.querySelectorAll('.chip');
    chips.forEach(function (c) {
      var k = c.dataset.kind;
      var n = live.filter(function (li) { return !k || li.dataset.kind === k; }).length;
      c.querySelector('em').textContent = n; if (k) c.hidden = !n;
      c.addEventListener('click', function () {
        chips.forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
        live.forEach(function (li) { li.hidden = !!k && li.dataset.kind !== k; });
      });
    });

    // Карточка события: открывается по адресу #e-<id>, закрывается крестиком, фоном или Esc.
    var shade = document.getElementById('shade'), last = null;
    var el = function (id) { return document.getElementById(id); };
    function fact(dt, dd) { return dd ? '<div><dt>' + dt + '</dt><dd></dd></div>' : ''; }
    function show() {
      var id = location.hash.slice(1), x = DATA[id];
      if (!x) { shade.hidden = true; document.body.classList.remove('locked'); if (last) { last.focus(); last = null; } return; }
      el('s-kind').textContent = x.kind;
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
    document.getElementById('evs').addEventListener('click', function (e) { var a = e.target.closest('.ev'); if (a) last = a; });
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
console.log(`standalone/christmas.html: ${list.length} событий (${kinds.map((k) => `${k.label} ${k.n}`).join(', ')})`);
if (noMap.length) console.log(`без карты (города нет в map-places.json): ${[...new Set(noMap)].join(', ')}`);
