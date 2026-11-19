#!/usr/bin/env node
/**
 * Сайт City Compas для хостинга (Cloudflare Pages) из событий Афиши — пока без остального сайта (DEC-W38, W39, W42).
 *   node scripts/build-site.mjs   → standalone/site/ (папка для загрузки) + standalone/christmas.html (страница для артефакта Claude)
 *   Архив для загрузки: cd standalone/site && zip -qr ../citycompas-site.zip .
 * Страницы (одинаковое устройство, разные подборки):
 *   /cyprus/afisha/     — вся афиша: события из недельной таблицы (scripts/import-week.py) и рождественские; фильтр «Что» — группы типов;
 *   /cyprus/christmas/  — Рождество: события с меткой christmas (scripts/import-christmas.py); «Что» — парки, деревни, огни, ярмарки.
 * Главная и короткие адреса временно (302) ведут на афишу (/christmas/ — на Рождество). Домен и название — SITE_URL, SITE_NAME
 * (по умолчанию https://citycompas.com и City Compas, DEC-W40). Превью для мессенджеров — standalone/og-<страница>.png.
 *
 * Устроено так, чтобы выдержать сотни событий:
 *  - три компактных фильтра в одну строку — выпадающие списки «Когда» (сегодня, завтра, эти и следующие выходные,
 *    любая дата сезона из своего календаря — без календаря браузера, который в рамках и на компьютере не открывался),
 *    «Где» (районы из src/data/regions.json), «Что» (виды) и «Сбросить», когда что-то выбрано;
 *  - один общий список: сначала ближайшее; то, что уже идёт (парки, выставки), стоит как «сегодня»;
 *    при выборе дня — однодневные события этого дня и всё долгое, что в этот день открыто;
 *  - видно несколько рядов, дальше — кнопка «Показать ещё N».
 * Плитки одного размера: понятное название (display_title, если задано), тип со значком, даты, город.
 * В карточке события — то же название и строкой ниже исходное. По нажатию — карточка события (адрес #e-<id>).
 * Единственная ссылка наружу — «Открыть на карте»: «место, город, Cyprus» из src/data/map-places.json
 * (латинское название заведения, которого нет в словаре, берётся как есть; русское — нет, ссылка ведёт на город).
 * Прошедшее скрывается по дате на Кипре, статус парков считается там же.
 */
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'yaml';

const DIR = path.resolve('src/content/events');
const OUT = path.resolve('standalone/christmas.html'); // страница для артефакта Claude (только Рождество)
const SITE_DIR = path.resolve('standalone/site');
const SITE_URL = (process.env.SITE_URL ?? 'https://citycompas.com').replace(/\/+$/, '');
const SITE_NAME = process.env.SITE_NAME ?? 'City Compas';
const MON = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const MON_FULL = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const WD_FULL = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
// [метка, фильтр, тип на плитке, тип в карточке события]. Вся страница про Рождество — на плитке тип короткий.
const KINDS = [
  ['christmas-parks', 'Парки', 'Парк', 'Рождественский парк'],
  ['christmas-villages', 'Деревни', 'Деревня', 'Рождественская деревня'],
  ['christmas-lights', 'Зажжение огней', 'Зажжение огней', 'Зажжение огней'],
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
const noMap = new Set(), unplaced = new Set();
const LATIN = /^[^\u0400-\u04FF]+$/;
const mapUrl = (e) => {
  const city = PLACES.cities[e.city] ?? PLACES.cities[e.city.split(/\s*[,/]\s*/)[0]];  // «Спилья, Троодос» → Спилья
  if (!city) { noMap.add(e.city); return null; }
  const venue = PLACES.venues[e.venue ?? ''] ?? (e.venue && LATIN.test(e.venue) ? e.venue : null);
  const q = [venue, city, 'Cyprus'].filter(Boolean).join(', ');
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

const YESTERDAY = new Date(Date.now() - 86400000).toLocaleDateString('en-CA', { timeZone: 'Europe/Nicosia' });
const ALL = fs.readdirSync(DIR).filter((f) => f.endsWith('.yaml'))
  .map((f) => ({ id: 'e-' + f.replace(/\.yaml$/, ''), ...parse(fs.readFileSync(path.join(DIR, f), 'utf8')) }))
  .filter((e) => e.status === 'published')
  // Давно прошедшее в файл не кладём (остальное прошедшее скрывает скрипт страницы по дате на Кипре).
  .filter((e) => (e.end_date ?? e.date) >= YESTERDAY);
const key = (e) => `${e.date}T${e.time ?? '00:00'}`;
const tags = (e) => e.tags ?? [];

// Значки типов — свои, линейные, 24×24; цвет берут от текста.
const ICONS = {
  park: '<circle cx="12" cy="9.5" r="6.5"/><circle cx="12" cy="9.5" r="1.2"/><path d="M12 3v5.3M12 10.7V16M5.5 9.5h5.3M13.2 9.5h5.3M10.8 15.9 8.5 21M13.2 15.9l2.3 5.1M6.5 21h11"/>',
  village: '<path d="M3.5 11 12 4l8.5 7M5.5 9.5V20h13V9.5M10 20v-5h4v5M15.5 6.9V4.5H18V9"/>',
  tree: '<path d="M12 3 7.5 9H10l-4 5.5h3.5L5 20h14l-4.5-5.5H18L14 9h2.5zM12 20v2"/>',
  market: '<path d="M4.5 4h15l2 5h-19zM9.5 4 9 9M14.5 4l.5 5M5 9v11M19 9v11M3 20h18M5 14h14"/>',
  workshop: '<circle cx="6.5" cy="17.5" r="3"/><circle cx="17.5" cy="17.5" r="3"/><path d="M8.6 15.4 17 3.5M15.4 15.4 7 3.5"/>',
  concert: '<circle cx="7.5" cy="17.5" r="3"/><path d="M10.5 17.5V4l7.5 3.5"/>',
  kids: '<path d="M12 16c-3.5 0-6-3.4-6-7a6 6 0 0 1 12 0c0 3.6-2.5 7-6 7zM11 17.5h2L12 16zM12 17.5c-1.5 1.5 1.5 2.5 0 4.5"/>',
  ticket: '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h13A1.5 1.5 0 0 1 20 7.5V10a2 2 0 0 0 0 4v2.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16.5V14a2 2 0 0 0 0-4z"/><path d="M14.5 6.5v2M14.5 11v2M14.5 15.5v2"/>',
  star: '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z"/>',
  mountain: '<path d="M3 19.5 9.5 8.5l4 6.5 2.5-3.8 5 8.3z"/><circle cx="17" cy="5.8" r="1.8"/>',
  pin: '<path d="M12 21s-6.5-5.6-6.5-10.5a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.3"/>',
  holiday: '<rect x="4" y="10.5" width="16" height="9.5" rx="1"/><rect x="3" y="7" width="18" height="3.5" rx="1"/><path d="M12 7v13M12 7c-1.2-3.2-5.5-3.6-4.8-.6M12 7c1.2-3.2 5.5-3.6 4.8-.6"/>',
};
const KIND_ICON = { 'christmas-parks': 'park', 'christmas-villages': 'village', 'christmas-lights': 'tree', 'christmas-markets': 'market', 'christmas-other': 'workshop' };
const svg = (k) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[k]}</svg>`;

// Рождество: вид — по меткам christmas-*; на плитке тип короткий, для «Мастер-классы и другое» — тип события.
const xmasKind = (e) => (KINDS.find(([t]) => tags(e).includes(t)) ?? KINDS[4]);
// Тип на плитке: вид из фильтра, а для «Мастер-классы и другое» — тип события из Афиши.
const OTHER_TYPES = { workshop: 'Мастер-класс', concert: 'Концерт', kids: 'Детям', theatre: 'Театр и шоу' };
const xmasType = (e, full) => (xmasKind(e)[0] === 'christmas-other' ? OTHER_TYPES[e.type] ?? 'Праздник' : xmasKind(e)[full ? 3 : 2]);

// Афиша: типы событий как на сайте (src/data/taxonomy.ts), сведённые в группы для фильтра.
const EVENT_TYPES = { concert: 'Концерт', theatre: 'Театр и шоу', standup: 'Стендап', festival: 'Фестиваль', exhibition: 'Выставка', cinema: 'Кино',
  kids: 'Детям', sport: 'Спорт', party: 'Вечеринка', tour: 'Экскурсия и прогулка', workshop: 'Мастер-класс', talk: 'Лекция и встреча', other: 'Другое' };
const GROUPS = [
  { t: 'g-music', label: 'Музыка и вечеринки', icon: 'concert', types: ['concert', 'party'] },
  { t: 'g-stage', label: 'Театр, стендап, кино', icon: 'ticket', types: ['theatre', 'standup', 'cinema'] },
  { t: 'g-kids', label: 'Детям', icon: 'kids', types: ['kids'] },
  { t: 'g-learn', label: 'Мастер-классы и лекции', icon: 'workshop', types: ['workshop', 'talk'] },
  { t: 'g-fest', label: 'Фестивали и выставки', icon: 'star', types: ['festival', 'exhibition'] },
  { t: 'g-active', label: 'Спорт и прогулки', icon: 'mountain', types: ['sport', 'tour'] },
  { t: 'g-other', label: 'Другое', icon: 'pin', types: ['other'] },
];
// На плитке — коротко, чтобы помещалось в строку; полностью — в карточке события.
const TYPE_SHORT = { tour: 'Экскурсия', talk: 'Лекция, встреча' };
const groupOf = (e) => GROUPS.find((g) => g.types.includes(e.type)) ?? GROUPS[GROUPS.length - 1];

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

const CHEV = '<svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
// Знак City Compas: метка на карте со стрелкой компаса (DEC-W41).
const MARK = '<rect width="32" height="32" rx="9" fill="#9fd5f2"/><path d="M16 3.6c-5.5 0-9.6 4.1-9.6 9.4 0 6.7 9.6 15.2 9.6 15.2s9.6-8.5 9.6-15.2c0-5.3-4.1-9.4-9.6-9.4z" fill="#0e1116"/><circle cx="16" cy="13" r="5.8" fill="#fff"/><path d="M19.4 9.6l-2.3 4.5-2.2-2.2z" fill="#f26b21"/><path d="M12.6 16.4l2.3-4.5 2.2 2.2z" fill="#0e1116"/>';

const BULBS = [[40, 19, '#ffd38a'], [95, 28, '#9fd5f2'], [150, 26, '#f26b21'], [205, 15, '#ffd38a'], [260, 21, '#7ee2b8'], [315, 28, '#9fd5f2'], [365, 21, '#f26b21'], [415, 14, '#ffd38a'], [470, 22, '#9fd5f2'], [520, 28, '#7ee2b8'], [570, 21, '#f26b21'], [620, 14, '#ffd38a'], [675, 22, '#9fd5f2'], [725, 27, '#f26b21'], [775, 15, '#ffd38a']];
const GARLAND = `  <svg class="garland" viewBox="0 0 800 50" preserveAspectRatio="none" aria-hidden="true">
    <path d="M0 8 Q100 42 200 14 T400 14 T600 14 T800 8" fill="none" stroke="#2a3a5c" stroke-width="2"/>
    ${BULBS.map(([x, y, c]) => `<circle class="bulb" cx="${x}" cy="${y}" r="4.5" fill="${c}"/>`).join('')}
  </svg>
`;
const TREE_SVG = `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS.tree}</svg>`;

const XMAS = {
  nav: 'Рождество на Кипре', tab: 'Рождество', tabIcon: 'tree', artifactUrl: 'https://claude.ai/artifact/LCR4o4541mrEkLVJNQg7Gi', path: '/cyprus/christmas/', og: 'standalone/og-christmas.png',
  title: 'Рождество на Кипре', ogTitle: 'Рождество на Кипре — сезон 2026–2027',
  description: 'Рождественские парки, деревни, ярмарки и праздники Кипра: даты, места и карта.',
  kicker: 'Сезон 2026–2027', h1: 'Рождество <em>на&nbsp;Кипре</em>', garland: true,
  events: ALL.filter((e) => tags(e).includes('christmas')),
  kinds: KINDS.map(([t, label]) => ({ t, label, icon: KIND_ICON[t] })),
  kindOf: (e) => xmasKind(e)[0],
  typeOf: xmasType,
  iconOf: (e) => (xmasKind(e)[0] === 'christmas-other' ? (ICONS[e.type] ? e.type : 'holiday') : KIND_ICON[xmasKind(e)[0]]),
};
const AFISHA = {
  nav: 'Афиша', tab: 'Афиша', tabIcon: 'concert', artifactUrl: 'https://claude.ai/artifact/7UMwUiLpWMgKEsAppxyroe', path: '/cyprus/afisha/', og: 'standalone/og-afisha.png',
  title: 'Афиша Кипра', ogTitle: 'Афиша Кипра — концерты, спектакли, фестивали',
  description: 'Концерты, спектакли, выставки, детские события и фестивали Кипра: даты, места и карта.',
  kicker: 'Что происходит', h1: 'Афиша <em>Кипра</em>', garland: false,
  events: ALL,
  kinds: GROUPS,
  kindOf: (e) => groupOf(e).t,
  typeOf: (e, full) => (!full && TYPE_SHORT[e.type]) || EVENT_TYPES[e.type] || 'Другое',
  iconOf: (e) => groupOf(e).icon,
  // Баннер Рождества — пока идёт сезон (скрипт страницы прячет его после последнего дня).
  banner: (artifact) => {
    const until = XMAS.events.reduce((m, e) => ((e.end_date ?? e.date) > m ? (e.end_date ?? e.date) : m), '');
    // В артефакте Claude ссылка ведёт на артефакт с Рождеством (относительные адреса сайта там не работают).
    const href = artifact ? `${XMAS_ARTIFACT}" target="_blank" rel="noopener` : XMAS.path;
    return until ? `  <a class="xbanner" href="${href}" data-until="${until}">${TREE_SVG}<span><b>Рождество на Кипре</b><small>Парки, рождественские деревни, ярмарки и зажжение огней</small></span><span class="go" aria-hidden="true">→</span></a>\n` : '';
  },
};
const PAGES = [AFISHA, XMAS];
const XMAS_ARTIFACT = XMAS.artifactUrl;

function buildPage(cfg, { artifact = false } = {}) {
  const list = [...cfg.events].sort((a, b) => key(a).localeCompare(key(b)));
  const kinds = cfg.kinds.map((k) => ({ ...k, n: list.filter((e) => cfg.kindOf(e) === k.t).length })).filter((k) => k.n);
  // Районы для фильтра: где есть события, по их числу; порядок при равенстве — как в regions.json.
  const regCount = new Map();
  for (const e of list) for (const r of regionsOfEvent(e)) regCount.set(r, (regCount.get(r) ?? 0) + 1);
  const regions = [...regCount.keys()].sort((a, b) => regCount.get(b) - regCount.get(a) || REG.regions.indexOf(a) - REG.regions.indexOf(b));
  for (const e of list) if (!regionsOfEvent(e).length) unplaced.add(e.city);


  const card = (e) => `
        <li data-kind="${cfg.kindOf(e)}" data-start="${e.date}" data-end="${e.end_date ?? e.date}" data-time="${e.time ?? ''}" data-reg="${esc(regionsOfEvent(e).join('|'))}"${isLong(e) ? ' data-long="1"' : ''}${e.open_days?.length ? ` data-days="${e.open_days.join(' ')}"` : ''}>
          <a class="ev" href="#${e.id}" data-id="${e.id}">
            <span class="ev-title">${esc(e.display_title ?? e.title)}</span>
            <span class="ev-meta">
              <span class="ev-type">${svg(cfg.iconOf(e))}${esc(cfg.typeOf(e, false))}</span>
              <span class="ev-date">${esc(dateShort(e))}</span>
              <span class="ev-city">${esc(e.city)}</span>
            </span>
          </a>
        </li>`;

  // Данные для карточки события — только публичные поля.
  const detail = Object.fromEntries(list.map((e) => [e.id, {
    kind: cfg.typeOf(e, true), icon: cfg.iconOf(e), group: cfg.kindOf(e), title: e.display_title ?? e.title, orig: e.display_title && e.display_title !== e.title ? e.title : '', when: whenFull(e), place: `${e.city}${e.venue ? ` · ${e.venue}` : ''}`,
    summary: e.summary ?? '', hours: e.hours ?? '', price: e.price ?? '', map: mapUrl(e),
    start: e.date, end: e.end_date ?? e.date, park: (e.tags ?? []).includes('christmas-parks'),
  }]));

  const html = `<title>${esc(cfg.title)}</title>
  <meta name="claude:viewport-fit-sides" content="cover">
  <meta name="description" content="${esc(cfg.description)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Unbounded:wght@600;700;800&display=swap">
  <style>
    /* Вечерний Кипр в декабре: ночное небо, гирлянда, голубой и оранжевый «Гида по Кипру». Сознательно одна тёмная тема.
       Раскладка: заголовок → строка фильтров → один список плиток; карточка события открывается поверх списка. */
    :root {
      color-scheme: dark;
      --night: #0a1120; --card: #111a2e; --card-hi: #16223b; --line: #22304d; --text: #eef3f9; --muted: #9fb0c8;
      --sky: #9fd5f2; --sun: #f26b21; --warm: #ffd38a; --ok: #7ee2b8;
      --gutter: max(16px, env(safe-area-inset-left, 0px));
      --display: "Unbounded", "Onest", system-ui, sans-serif; --body: "Onest", system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    html { background: var(--night); }
    body { margin: 0; background: var(--night); color: var(--text); font-family: var(--body); font-size: 16px; line-height: 1.5;
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
  
    /* У каждого вида свой цвет: парки — оранжевый, деревни — голубой, зажжение огней — зелёный, ярмарки — жёлтый, остальное — сиреневый. */
    [data-kind="christmas-parks"] { --c: #ffa463; } [data-kind="christmas-villages"] { --c: #8fd0f5; } [data-kind="christmas-lights"] { --c: #6fe3a5; }
    [data-kind="christmas-markets"] { --c: #ffd166; } [data-kind="christmas-other"] { --c: #c4b0ff; }
    /* Группы афиши: музыка — голубой, театр — оранжевый, детям — розовый, мастер-классы — сиреневый,
       фестивали — жёлтый, спорт и прогулки — зелёный, остальное — серо-голубой. */
    [data-kind="g-music"] { --c: #8fd0f5; } [data-kind="g-stage"] { --c: #ffa463; } [data-kind="g-kids"] { --c: #ff9ec4; }
    [data-kind="g-learn"] { --c: #c4b0ff; } [data-kind="g-fest"] { --c: #ffd166; } [data-kind="g-active"] { --c: #6fe3a5; } [data-kind="g-other"] { --c: #a9b8cc; }
    .top { height: 14px; }
    /* Верхняя полоса с разделами: всегда под рукой, при прокрутке остаётся сверху. */
    .topbar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 12; display: flex; align-items: center; justify-content: space-between; gap: 10px;
      padding-block: 10px; background: var(--night); border-bottom: 1px solid transparent; }
    .topbar.stuck { border-bottom-color: var(--line); }
    .tb-brand { display: inline-flex; align-items: center; gap: 8px; min-width: 0; color: var(--text); text-decoration: none; font-family: var(--display); font-weight: 600; font-size: .86rem; white-space: nowrap; }
    @media (min-width: 640px) { .tb-brand { font-size: .95rem; } }
    .tb-brand svg { flex: none; }
    @media (max-width: 379px) { .tb-brand span { display: none; } }
    .tabs { display: flex; gap: 3px; padding: 3px; background: var(--card); border: 1px solid var(--line); border-radius: 999px; }
    .tabs a { display: inline-flex; align-items: center; gap: 5px; padding: 7px 10px; border-radius: 999px; color: var(--muted); font: 600 .86rem var(--body); text-decoration: none; white-space: nowrap; }
    @media (min-width: 640px) { .tabs a { padding: 7px 13px; font-size: .9rem; } }
    .tabs a .ic { width: 16px; height: 16px; color: var(--c, var(--sky)); }
    @media (max-width: 419px) { .tabs a .ic { display: none; } }  /* на узком телефоне — только слова, чтобы название не прижималось */
    .tabs a:hover { color: var(--text); }
    .tabs a[aria-current] { background: var(--text); color: var(--night); }
    .tabs a[aria-current] .ic { color: inherit; }
    .tb-brand:focus-visible, .tabs a:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }
    .xbanner { display: flex; align-items: center; gap: 12px; margin: 0 0 18px; padding: 12px 16px; border-radius: 16px; text-decoration: none; color: var(--text);
      background: linear-gradient(100deg, #17284a, #0f1a30); border: 1px solid #2b3f66; }
    .xbanner[hidden] { display: none; }
    .xbanner .ic { width: 28px; height: 28px; color: #6fe3a5; }
    .xbanner b { display: block; font-family: var(--display); font-weight: 700; font-size: 1rem; }
    .xbanner small { display: block; color: var(--muted); font-size: .86rem; }
    .xbanner .go { margin-left: auto; color: var(--warm); font-size: 1.3rem; }
    .xbanner:hover { border-color: #3d5689; }
    .fnav { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 4px; }
    .fnav a { color: var(--sky); text-underline-offset: 3px; } .fnav span { color: var(--text); }
  
    /* Фильтры: три выпадающих списка в одну строку. Видна кнопка-«таблетка» с выбранным значением,
       поверх неё — прозрачный <select>, поэтому на телефоне открывается родной выбор. */
    .filters { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
    @media (min-width: 640px) { .filters { gap: 8px; } }
    .pick { position: relative; display: inline-flex; align-items: center; gap: 3px; padding: 8px 8px 8px 11px; border: 1px solid var(--line); border-radius: 999px;
      background: var(--card); color: var(--text); font: 600 .88rem var(--body); white-space: nowrap; cursor: pointer; }
    @media (min-width: 640px) { .pick { gap: 6px; padding: 9px 11px 9px 14px; font-size: .9rem; } }
    .pick:hover { border-color: #3a4d74; }
    .pick select { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; font-size: 16px; border: 0; appearance: none; }
    .pick .chev { flex: none; width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; opacity: .7; }
    .pick-ic:empty { display: none; } .pick-ic { display: inline-flex; } .pick-ic .ic { width: 18px; height: 18px; }
    .pick.on { background: var(--c, var(--text)); border-color: var(--c, var(--text)); color: #0a1120; }
    .pick:focus-within { outline: 2px solid var(--warm); outline-offset: 2px; }
    .clear { font: 600 .9rem var(--body); color: var(--sky); background: none; border: 0; padding: 8px 4px; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
    .clear[hidden] { display: none; }
    /* Свой календарь для «Выбрать дату…»: одинаково работает на компьютере, телефоне и внутри чужой рамки. */
    .cal { position: absolute; top: calc(100% + 8px); left: 0; z-index: 15; width: 300px; max-width: 100%; box-sizing: border-box; padding: 12px;
      background: var(--card); border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 14px 34px rgba(0, 0, 0, .5); }
    .cal[hidden] { display: none; }
    .cal-h { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-weight: 700; }
    .cal-nav { width: 36px; height: 36px; border-radius: 999px; border: 1px solid var(--line); background: transparent; color: var(--text); font-size: 1.25rem; line-height: 1; cursor: pointer; }
    .cal-nav:disabled { opacity: .3; cursor: default; }
    .cal-g { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; text-align: center; }
    .cal-g .wd { font-size: .74rem; color: var(--muted); padding: 2px 0 4px; }
    .cal-g button { position: relative; height: 38px; border: 0; border-radius: 10px; background: transparent; color: var(--text); font: 600 .92rem var(--body); cursor: pointer; }
    .cal-g button:hover:not(:disabled) { background: var(--card-hi); }
    .cal-g button:disabled { color: #4a5875; cursor: default; }
    .cal-g button.today { box-shadow: inset 0 0 0 1px var(--sky); }
    .cal-g button.has::after { content: ""; position: absolute; left: 50%; bottom: 4px; width: 4px; height: 4px; margin-left: -2px; border-radius: 50%; background: var(--warm); }
    .cal-g button.sel { background: var(--text); color: var(--night); }
    .cal-nav:focus-visible, .cal-g button:focus-visible { outline: 2px solid var(--warm); outline-offset: 1px; }
  
    #list { margin-top: 20px; }
    .more { display: block; width: 100%; max-width: 340px; margin: 14px auto 0; padding: 11px 16px; border-radius: 999px; border: 1px solid var(--line); background: transparent; color: var(--text); font: 600 .92rem var(--body); cursor: pointer; }
    .more[hidden] { display: none; }
    .more:hover { border-color: #3a4d74; background: var(--card); }
    .empty { margin: 12px 0 0; color: var(--muted); }
    .empty button { font: 600 1rem var(--body); color: var(--sky); background: none; border: 0; padding: 0; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
  
    /* Плитки одного размера: название без хвоста (до 3 строк), под ним тип, даты, город. 2 в ряд на телефоне, 3–4 на компьютере. */
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
    .xbanner:focus-visible, .fnav a:focus-visible, .ev:focus-visible, .clear:focus-visible, .more:focus-visible, .empty button:focus-visible, .sheet button:focus-visible, .sheet a:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }
  
    /* Карточка события */
    .shade[hidden] { display: none; }
    .shade { position: fixed; inset: 0; z-index: 20; background: rgba(4, 8, 16, .66); display: flex; align-items: flex-end; justify-content: center; }
    .sheet { position: relative; width: 100%; max-width: 620px; max-height: calc(100% - 40px); overflow: auto; background: var(--card); border: 1px solid var(--line);
      border-radius: 22px 22px 0 0; padding: 22px max(20px, env(safe-area-inset-right, 0px)) calc(24px + env(safe-area-inset-bottom, 0px)) max(20px, env(safe-area-inset-left, 0px)); display: grid; gap: 12px; }
    @media (min-width: 700px) { .shade { align-items: center; } .sheet { border-radius: 22px; padding: 26px 28px; } }
    .close { position: absolute; top: 12px; right: 12px; width: 38px; height: 38px; border-radius: 999px; border: 1px solid var(--line); background: var(--night); color: var(--text); font-size: 1.3rem; line-height: 1; cursor: pointer; }
    .s-kind { display: flex; align-items: center; gap: 8px; font-size: .76rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--c, var(--sky)); padding-right: 44px; }
    .sheet h2 { font-family: var(--display); font-weight: 700; font-size: 1.35rem; line-height: 1.2; margin: 0; padding-right: 36px; text-wrap: balance; }
    .s-orig { margin: -6px 0 0; color: var(--muted); font-size: .9rem; }
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
  <nav class="topbar" aria-label="Разделы">
    <a class="tb-brand" href="${artifact ? AFISHA.artifactUrl + '" target="_blank" rel="noopener' : AFISHA.path}"><svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">${MARK}</svg><span>${esc(SITE_NAME)}</span></a>
    <div class="tabs">${PAGES.map((p) => p === cfg
      ? `<a href="#" aria-current="page" data-kind="${p === XMAS ? 'christmas-lights' : ''}">${svg(p.tabIcon)}${esc(p.tab)}</a>`
      : `<a href="${artifact ? p.artifactUrl + '" target="_blank" rel="noopener' : p.path}" data-kind="${p === XMAS ? 'christmas-lights' : ''}">${svg(p.tabIcon)}${esc(p.tab)}</a>`).join('')}</div>
  </nav>
  ${cfg.garland ? GARLAND : '  <div class="top"></div>\n'}  <header>
      <p class="kicker">${cfg.kicker}</p>
      <h1>${cfg.h1}</h1>
    </header>
  ${cfg.banner ? cfg.banner(artifact) : ''}
    <div class="filters" role="group" aria-label="Фильтры">
      <label class="pick"><span class="pick-t">Все дни</span>${CHEV}<select id="f-date" aria-label="Когда"><option value="">Все дни</option></select></label>
      <label class="pick"><span class="pick-t">Весь Кипр</span>${CHEV}<select id="f-reg" aria-label="Где"><option value="">Весь Кипр</option>${regions.map((r) => `<option value="${esc(r)}">${esc(r)}</option>`).join('')}</select></label>
      <label class="pick"><span class="pick-ic"></span><span class="pick-t">Все события</span>${CHEV}<select id="f-kind" aria-label="Что"><option value="">Все события</option>${kinds.map((k) => `<option value="${k.t}">${k.label}</option>`).join('')}</select></label>
      <button type="button" class="clear" id="clear" hidden>Сбросить</button>
      <div class="cal" id="cal" role="dialog" aria-label="Выберите дату" hidden>
        <div class="cal-h"><button type="button" class="cal-nav" id="cal-prev" aria-label="Предыдущий месяц">‹</button><b id="cal-m"></b><button type="button" class="cal-nav" id="cal-next" aria-label="Следующий месяц">›</button></div>
        <div class="cal-g" id="cal-g"></div>
      </div>
    </div>
  
    <div id="list">
      <ul class="evs" id="evs">${list.map(card).join('')}
      </ul>
      <button type="button" class="more" id="more" hidden></button>
      <p class="empty" id="empty" hidden>Ничего не нашлось. <button type="button" id="reset">Сбросить фильтры</button></p>
    </div>
  
    <footer>
      <span class="brand"><svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">${MARK}</svg>${esc(SITE_NAME)}</span>
      <span>${esc(SITE_NAME)} — гид по Кипру на русском: что происходит, куда сходить и к кому обратиться.</span>${artifact ? '' : `
      <nav class="fnav" aria-label="Разделы">${PAGES.map((p) => p === cfg ? `<span>${esc(p.nav)}</span>` : `<a href="${p.path}">${esc(p.nav)}</a>`).join('')}</nav>`}
    </footer>
  </div>
  
  <div class="shade" id="shade" hidden>
    <div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="s-title">
      <button type="button" class="close" id="s-close" aria-label="Закрыть">×</button>
      <span class="s-kind" id="s-kind"></span>
      <h2 id="s-title"></h2>
      <p class="s-orig" id="s-orig" hidden></p>
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
      var ICONS = ${JSON.stringify(Object.fromEntries(Object.keys(ICONS).map((k) => [k, svg(k)])))}, KIND_ICON = ${JSON.stringify(Object.fromEntries(cfg.kinds.map((k) => [k.t, k.icon])))};
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
  
      // Полоса с разделами получает нижнюю линию, когда страницу прокрутили.
    var bar = document.querySelector('.topbar');
    if (bar) { var onScroll = function () { bar.classList.toggle('stuck', window.scrollY > 4); }; window.addEventListener('scroll', onScroll, { passive: true }); onScroll(); }
    all('.tabs a[aria-current]').forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }); });
    // Прошедшее убираем; баннер Рождества — до конца сезона.
      all('.xbanner').forEach(function (b) { if (b.dataset.until < today) b.hidden = true; });
      all('#evs > li').forEach(function (li) { if (li.dataset.end < today) li.remove(); });
      var items = all('#evs > li'), list = el('evs');
  
      // «Когда»: периоды, понятные в любой день сезона — сегодня, завтра, эти и следующие выходные, любая дата из календаря.
      var shortD = function (iso) { return d(iso).getUTCDate() + ' ' + MON_S[d(iso).getUTCMonth()]; };
      var dayLabel = function (iso) { return WD[d(iso).getUTCDay()] + ', ' + shortD(iso); };
      var span = function (a) {
        var x = a[0], y = a[a.length - 1];
        if (x === y) return dayLabel(x);
        return d(x).getUTCMonth() === d(y).getUTCMonth() ? d(x).getUTCDate() + '–' + shortD(y) : shortD(x) + ' – ' + shortD(y);
      };
      // Ближайшие выходные начиная с дня iso; в воскресенье — только оно.
      var weekend = function (iso) { var wd = d(iso).getUTCDay(); if (wd === 0) return [iso]; var sat = plus(iso, 6 - wd); return [sat, plus(sat, 1)]; };
      var seasonEnd = items.reduce(function (m, li) { return li.dataset.end > m ? li.dataset.end : m; }, today);
      var we1 = weekend(today), we2 = weekend(plus(we1[we1.length - 1], 1));
      var PERIODS = { today: [today], tomorrow: [tomorrow], we1: we1, we2: we2 };
      var picks = { date: el('f-date'), reg: el('f-reg'), kind: el('f-kind') };
      var addOpt = function (v, text, short) {
        var o = document.createElement('option'); o.value = v; o.textContent = text; if (short) o.dataset.short = short;
        picks.date.appendChild(o); return o;
      };
      addOpt('today', 'Сегодня'); addOpt('tomorrow', 'Завтра');
      if (we1[0] <= seasonEnd) addOpt('we1', 'Эти выходные · ' + span(we1), 'Выходные');
      if (we2[0] <= seasonEnd) addOpt('we2', 'Следующие выходные · ' + span(we2), 'След. выходные');
      var pickOpt = addOpt('pick', 'Выбрать дату…');
  
      var state = { date: '', days: null, reg: '', kind: '' }, shown = 0;
      var openOn = function (li, x) { return li.dataset.days ? li.dataset.days.split(' ').indexOf(x) >= 0 : li.dataset.start <= x && x <= li.dataset.end; };
      var match = function (li, s) {
        if (s.kind && li.dataset.kind !== s.kind) return false;
        if (s.reg && li.dataset.reg.split('|').indexOf(s.reg) < 0) return false;
        // Однодневное — если оно в один из выбранных дней; долгое — если в один из них открыто (у деревень — дни из open_days).
        if (s.days) return s.days.some(function (x) { return li.dataset.long ? openOn(li, x) : li.dataset.start === x; });
        return true;
      };
      // Районы и виды без событий (после того как прошедшее убрано) не показываем.
      all('#f-reg option, #f-kind option').forEach(function (o) {
        if (!o.value) return;
        var probe = { date: '', days: null, reg: '', kind: '' }; probe[o.parentNode.id === 'f-reg' ? 'reg' : 'kind'] = o.value;
        if (!items.some(function (li) { return match(li, probe); })) o.remove();
      });
      // Таблетка показывает выбранное; выбранный вид — его цветом и значком.
      function sync() {
        Object.keys(picks).forEach(function (k) {
          var sel = picks[k], lab = sel.parentNode;
          var opt = sel.options[sel.selectedIndex];
          lab.querySelector('.pick-t').textContent = opt.dataset.short || opt.text;
          lab.classList.toggle('on', !!sel.value);
        });
        var kl = picks.kind.parentNode;
        if (state.kind) { kl.dataset.kind = state.kind; kl.querySelector('.pick-ic').innerHTML = ICONS[KIND_ICON[state.kind]]; }
        else { delete kl.dataset.kind; kl.querySelector('.pick-ic').innerHTML = ''; }
        el('clear').hidden = !(state.date || state.reg || state.kind);
      }
  
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
        var from = state.days ? state.days[0] : today, eff = li.dataset.start < from ? from : li.dataset.start;
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
      Object.keys(picks).forEach(function (k) {
        picks[k].addEventListener('change', function () {
          var v = picks[k].value;
          if (k === 'date' && v === 'pick') { picks.date.value = state.date; openCal(); return; }
          state[k] = v;
          if (k === 'date') { state.days = !v ? null : PERIODS[v] || [v.slice(2)]; closeCal(); }
          sync(); render();
        });
      });
      // «Выбрать дату…»: свой календарь в пределах сезона (с сегодняшнего дня до конца последнего события).
      // Точкой отмечены дни, на которые есть однодневные события.
      var MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
      var eventDays = {}; items.forEach(function (li) { if (!li.dataset.long) eventDays[li.dataset.start] = 1; });
      var cal = el('cal'), calYM = today.slice(0, 7);
      var ym = function (iso, n) { var y = +iso.slice(0, 4), m = +iso.slice(5, 7) - 1 + n; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + (m < 9 ? '0' : '') + (m + 1); };
      function drawCal() {
        var y = +calYM.slice(0, 4), m = +calYM.slice(5, 7) - 1;
        el('cal-m').textContent = MONTHS[m] + ' ' + y;
        el('cal-prev').disabled = calYM <= today.slice(0, 7);
        el('cal-next').disabled = calYM >= seasonEnd.slice(0, 7);
        var g = el('cal-g'), html = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(function (w) { return '<span class="wd">' + w + '</span>'; }).join('');
        var lead = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7, n = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
        for (var i = 0; i < lead; i++) html += '<span></span>';
        var sel = state.days && state.days.length === 1 ? state.days[0] : '';
        for (var dd = 1; dd <= n; dd++) {
          var iso = calYM + '-' + (dd < 10 ? '0' : '') + dd, off = iso < today || iso > seasonEnd;
          var cls = [iso === today ? 'today' : '', eventDays[iso] ? 'has' : '', iso === sel ? 'sel' : ''].join(' ').trim();
          html += '<button type="button" data-d="' + iso + '"' + (cls ? ' class="' + cls + '"' : '') + (off ? ' disabled' : '') + ' aria-label="' + dayLabel(iso) + '">' + dd + '</button>';
        }
        g.innerHTML = html;
      }
      function openCal() {
        calYM = state.days ? state.days[0].slice(0, 7) : today.slice(0, 7);
        drawCal(); cal.hidden = false;
        var b = cal.querySelector('.cal-g button.sel') || cal.querySelector('.cal-g button:not(:disabled)'); if (b) b.focus();
      }
      function closeCal() { cal.hidden = true; }
      el('cal-prev').addEventListener('click', function () { calYM = ym(calYM, -1); drawCal(); });
      el('cal-next').addEventListener('click', function () { calYM = ym(calYM, 1); drawCal(); });
      el('cal-g').addEventListener('click', function (e) {
        var b = e.target.closest('button[data-d]'); if (!b || b.disabled) return;
        var iso = b.dataset.d;
        all('#f-date option').forEach(function (o) { if (o.value.indexOf('d:') === 0) o.remove(); });
        var v = iso === today ? 'today' : iso === tomorrow ? 'tomorrow' : 'd:' + iso;
        if (v.indexOf('d:') === 0) { var o = document.createElement('option'); o.value = v; o.textContent = dayLabel(iso); picks.date.insertBefore(o, pickOpt); }
        picks.date.value = v; state.date = v; state.days = [iso];
        closeCal(); sync(); render(); picks.date.focus();
      });
      document.addEventListener('click', function (e) { if (!cal.hidden && !cal.contains(e.target) && e.target !== picks.date) closeCal(); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !cal.hidden) { closeCal(); picks.date.focus(); } });
      el('more').addEventListener('click', function () { shown += page(); render(true); });
      function resetAll() {
        state = { date: '', days: null, reg: '', kind: '' };
        Object.keys(picks).forEach(function (k) { picks[k].value = ''; });
        closeCal();
        sync(); render();
      }
      el('reset').addEventListener('click', resetAll);
      el('clear').addEventListener('click', resetAll);
      sync(); render();
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
        el('s-orig').textContent = x.orig; el('s-orig').hidden = !x.orig;
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
  return { html, list, kinds, regions, regCount };
}

// Страницы для артефактов Claude (предпросмотр) — без ссылок на разделы сайта.
fs.mkdirSync(path.dirname(OUT), { recursive: true });
for (const [cfg, file] of [[XMAS, OUT], [AFISHA, path.resolve('standalone/afisha.html')]]) {
  const art = buildPage(cfg, { artifact: true });
  fs.writeFileSync(file, art.html);
  console.log(`${path.relative(process.cwd(), file)}: ${art.list.length} событий`);
}

// Папка для хостинга: полноценные HTML-документы с превью для мессенджеров.
fs.rmSync(SITE_DIR, { recursive: true, force: true });
for (const cfg of PAGES) {
  const { html, list, kinds, regions, regCount } = buildPage(cfg);
  const cutAt = html.indexOf('</style>\n') + '</style>\n'.length;
  const head = html.slice(0, cutAt).replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '');
  const doc = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#0a1120">
<meta property="og:type" content="website">
<meta property="og:locale" content="ru_RU">
<meta property="og:site_name" content="${esc(SITE_NAME)}">
<meta property="og:title" content="${esc(cfg.ogTitle)}">
<meta property="og:description" content="${esc(cfg.description)}">${SITE_URL ? `
<meta property="og:url" content="${SITE_URL}${cfg.path}">
<link rel="canonical" href="${SITE_URL}${cfg.path}">
<meta property="og:image" content="${SITE_URL}${cfg.path}og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">` : ''}
${head}</head>
<body>
${html.slice(cutAt)}</body>
</html>
`;
  fs.mkdirSync(path.join(SITE_DIR, cfg.path), { recursive: true });
  fs.writeFileSync(path.join(SITE_DIR, cfg.path, 'index.html'), doc);
  fs.copyFileSync(path.resolve(cfg.og), path.join(SITE_DIR, cfg.path, 'og.png'));
  console.log(`site${cfg.path}: ${list.length} событий (${kinds.map((k) => `${k.label} ${k.n}`).join(', ')}); районы: ${regions.map((r) => `${r} ${regCount.get(r)}`).join(', ')}`);
}
fs.copyFileSync(path.resolve('public/favicon.svg'), path.join(SITE_DIR, 'favicon.svg'));
// 302 — временно: главная потом станет главной основного сайта, а браузеры не запомнят переадресацию навсегда.
fs.writeFileSync(path.join(SITE_DIR, '_redirects'), [
  `/ ${AFISHA.path} 302`, `/cyprus ${AFISHA.path} 302`, `/cyprus/ ${AFISHA.path} 302`, `/afisha ${AFISHA.path} 302`, `/afisha/ ${AFISHA.path} 302`,
  `/christmas ${XMAS.path} 302`, `/christmas/ ${XMAS.path} 302`, '',
].join('\n'));
fs.writeFileSync(path.join(SITE_DIR, '404.html'), `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Страница не найдена</title><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a1120;color:#eef3f9;font:16px/1.5 system-ui,sans-serif;padding:16px}a{color:#ffd38a}</style>
</head><body><p>Такой страницы нет. <a href="${AFISHA.path}">Афиша Кипра</a> · <a href="${XMAS.path}">Рождество на Кипре</a></p></body></html>
`);
console.log(`standalone/site/ — для ${SITE_URL}`);
if (unplaced.size) console.log(`без района (места нет в regions.json): ${[...unplaced].join(', ')}`);
if (noMap.size) console.log(`без карты (города нет в map-places.json): ${[...noMap].join(', ')}`);
