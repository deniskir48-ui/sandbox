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
  ['christmas-other', 'Другое', 'Праздник', 'Праздник'],
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
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4M7.5 14h2M11 14h2M14.5 14h2M7.5 17h2M11 17h2"/>',
  pin: '<path d="M12 21s-6.5-5.6-6.5-10.5a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.3"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
  share: '<path d="M12 3.5v12M7.5 8 12 3.5 16.5 8M5 12.5v6A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-6"/>',
  plus: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4M12 12.5v5M9.5 15h5"/>',
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
  { t: 'g-kids', label: 'Детям', icon: 'kids', types: ['kids'] },
  { t: 'g-music', label: 'Музыка', icon: 'concert', types: ['concert', 'party'] },
  { t: 'g-stage', label: 'Театр и кино', icon: 'ticket', types: ['theatre', 'standup', 'cinema'] },
  { t: 'g-fest', label: 'Фестивали', icon: 'star', types: ['festival', 'exhibition'] },
  { t: 'g-learn', label: 'Мастер-классы', icon: 'workshop', types: ['workshop', 'talk'] },
  { t: 'g-active', label: 'Спорт и туры', icon: 'mountain', types: ['sport', 'tour'] },
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
  return `${full(e.date)}, ${WD_FULL[day(e.date).getUTCDay()]}${e.time ? `, ${e.time}${e.end_time ? `–${e.end_time}` : ''}` : ''}`;
};
// Факты карточки события в порядке чтения; пустые не показываются.
const facts = (e) => [
  ['Когда', whenFull(e)], ['Сеансы', e.sessions], ['Ещё даты', e.more_dates], ['Где', `${e.city}${e.venue ? ` · ${e.venue}` : ''}`], ['Адрес', e.address],
  ['Часы', e.hours], ['Стоимость', e.price], ['Язык', e.language], ['Возраст', e.age], ['Запись', e.booking],
].filter(([, v]) => v);

const isLong = (e) => !!e.end_date && e.end_date !== e.date;
// Метки на плитке (как «бесплатно» и «сегодня» на больших афишах): только когда это прямо сказано в данных события.
const isFree = (e) => (e.price ? /бесплатн|свободн|free/i.test(e.price) && !/\d/.test(e.price)
  : /бесплатн|вход свободный|free entry/i.test(e.summary ?? '') && !/€/.test(e.summary ?? ''));
const isRu = (e) => /русск/i.test(e.language ?? '') || /русскоязычн|на русском/i.test(`${e.title} ${e.display_title ?? ''} ${e.summary ?? ''} ${e.description ?? ''}`);
// Текст для поиска: название, оригинальное название, место, город (строчными, ё → е).
// Латинские названия ищутся и русскими буквами: «каста» находит Kasta, «кевин» — Kevin de Vries (грубая транслитерация).
const LAT = [['sch', 'щ'], ['sh', 'ш'], ['ch', 'ч'], ['zh', 'ж'], ['kh', 'х'], ['ts', 'ц'], ['ya', 'я'], ['yu', 'ю'], ['yo', 'ё'], ['th', 'т'], ['ph', 'ф'], ['ck', 'к'], ['ou', 'у'], ['oo', 'у'], ['ee', 'и'],
  ['a', 'а'], ['b', 'б'], ['c', 'к'], ['d', 'д'], ['e', 'е'], ['f', 'ф'], ['g', 'г'], ['h', 'х'], ['i', 'и'], ['j', 'дж'], ['k', 'к'], ['l', 'л'], ['m', 'м'], ['n', 'н'], ['o', 'о'], ['p', 'п'], ['q', 'к'], ['r', 'р'], ['s', 'с'], ['t', 'т'], ['u', 'у'], ['v', 'в'], ['w', 'в'], ['x', 'кс'], ['y', 'и'], ['z', 'з']];
const translit = (t) => { let r = t.toLowerCase(); for (const [a, b] of LAT) r = r.split(a).join(b); return r; };
const searchText = (e, cfg) => { const base = `${e.display_title ?? ''} ${e.title} ${e.venue ?? ''} ${e.city} ${cfg.typeOf(e, true)}`.toLowerCase();
  const lat = base.match(/[a-z][a-z' -]+/g)?.join(' ') ?? '';
  return `${base} ${translit(lat)}`.replace(/ё/g, 'е').replace(/\s+/g, ' ').trim(); };
// Разметка schema.org Event для поисковиков (страница сайта; в артефакте не нужна).
const jsonLd = (list, cfg) => JSON.stringify(list.map((e) => {
  const t = (iso, hm) => (hm ? `${iso}T${hm}:00+02:00` : iso);
  return {
    '@context': 'https://schema.org', '@type': 'Event', name: e.display_title ?? e.title,
    startDate: t(e.date, isLong(e) ? null : e.time), endDate: isLong(e) ? e.end_date : t(e.date, e.end_time ?? null),
    eventStatus: 'https://schema.org/EventScheduled', eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
    location: { '@type': 'Place', name: e.venue ?? e.city, address: { '@type': 'PostalAddress', streetAddress: e.address, addressLocality: e.city, addressCountry: 'CY' } },
    description: (e.description ?? e.summary ?? '').slice(0, 300), url: `${SITE_URL}${cfg.path}#${e.id}`,
    ...(isFree(e) ? { isAccessibleForFree: true, offers: { '@type': 'Offer', price: 0, priceCurrency: 'EUR' } } : {}),
  };
})).replace(/</g, '\\u003c');

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
  // С рождественской страницы (на неё ведут посты) — заметный переход ко всей афише.
  banner: (artifact) => {
    const href = artifact ? `${AFISHA.artifactUrl}" target="_blank" rel="noopener` : AFISHA.path;
    return `  <a class="xbanner to-afisha" href="${href}"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS.calendar}</svg><span><b>Вся афиша Кипра</b><small>Концерты, спектакли, выставки и детские события на неделю</small></span><span class="go" aria-hidden="true">→</span></a>\n`;
  },
};
const AFISHA = {
  nav: 'Афиша', tab: 'Афиша', tabIcon: 'calendar', artifactUrl: 'https://claude.ai/artifact/7UMwUiLpWMgKEsAppxyroe', path: '/cyprus/afisha/', og: 'standalone/og-afisha.png',
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
  const list = [...cfg.events].sort((a, b) => (a.priority ?? 3) - (b.priority ?? 3) || key(a).localeCompare(key(b)));
  const kinds = cfg.kinds.map((k) => ({ ...k, n: list.filter((e) => cfg.kindOf(e) === k.t).length })).filter((k) => k.n);
  // Районы для фильтра: где есть события, по их числу; порядок при равенстве — как в regions.json.
  const regCount = new Map();
  for (const e of list) for (const r of regionsOfEvent(e)) regCount.set(r, (regCount.get(r) ?? 0) + 1);
  const regions = [...regCount.keys()].sort((a, b) => regCount.get(b) - regCount.get(a) || REG.regions.indexOf(a) - REG.regions.indexOf(b));
  for (const e of list) if (!regionsOfEvent(e).length) unplaced.add(e.city);


  // Атрибуты для фильтров — одни и те же у плитки списка и у карточки «Главного».
  const attrs = (e) => `data-id="${e.id}" data-kind="${cfg.kindOf(e)}" data-start="${e.date}" data-end="${e.end_date ?? e.date}" data-time="${e.time ?? ''}" data-prio="${e.priority ?? 3}" data-reg="${esc(regionsOfEvent(e).join('|'))}"${isLong(e) ? ' data-long="1"' : ''}${e.open_days?.length ? ` data-days="${e.open_days.join(' ')}"` : ''}${isFree(e) ? ' data-free="1"' : ''}${isRu(e) ? ' data-ru="1"' : ''} data-q="${esc(searchText(e, cfg))}"`;
  const tagsOf = (e) => (isFree(e) || isRu(e) ? `<span class="ev-tags">${isFree(e) ? '<span class="tag free">Бесплатно</span>' : ''}${isRu(e) ? '<span class="tag ru">На русском</span>' : ''}</span>` : '');
  const card = (e) => `
        <li ${attrs(e)}>
          <a class="ev" href="#${e.id}" data-id="${e.id}">
            <span class="ev-title">${esc(e.display_title ?? e.title)}</span>
            <span class="ev-meta">
              <span class="ev-type">${svg(cfg.iconOf(e))}${esc(cfg.typeOf(e, false))}</span>
              <span class="ev-date">${esc(dateShort(e))}</span>
              <span class="ev-city">${esc(e.city)}</span>${tagsOf(e)}
            </span>
          </a>
        </li>`;
  // «Главное» — события первого приоритета из таблицы недели: крупнее, с одной строкой о том, что будет.
  const pickCard = (e) => `
        <a class="pc" href="#${e.id}" ${attrs(e)} hidden>
          <span class="ev-type">${svg(cfg.iconOf(e))}${esc(cfg.typeOf(e, false))}</span>
          <span class="pc-title">${esc(e.display_title ?? e.title)}</span>
          ${e.summary ? `<span class="pc-why">${esc(e.summary)}</span>` : ''}
          <span class="pc-foot"><span class="ev-date">${esc(dateShort(e))}</span><span class="ev-city">${esc(e.city)}</span>${tagsOf(e)}</span>
        </a>`;
  const toggles = { free: list.some(isFree), ru: list.some(isRu) };

  // Данные для карточки события — только публичные поля.
  const detail = Object.fromEntries(list.map((e) => [e.id, {
    kind: cfg.typeOf(e, true), icon: cfg.iconOf(e), group: cfg.kindOf(e), title: e.display_title ?? e.title, orig: e.display_title && e.display_title !== e.title ? e.title : '', facts: facts(e),
    // Подробное описание из источников (description), если есть; иначе — строка из таблицы.
    summary: e.description ?? e.summary ?? '', map: mapUrl(e),
    start: e.date, end: e.end_date ?? e.date, park: (e.tags ?? []).includes('christmas-parks'),
    // Для «В календарь»: время, место одной строкой.
    time: e.time ?? '', endTime: e.end_time ?? '', place: `${e.venue ? `${e.venue}, ` : ''}${e.address && !e.venue ? `${e.address}, ` : ''}${e.city}`,
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
    .wrap { max-width: 1240px; margin: 0 auto; }
    .garland { display: block; width: 100%; height: 26px; margin-top: 2px; }
    .bulb { animation: tw 3.2s ease-in-out infinite; } .bulb:nth-child(3n) { animation-delay: .8s; } .bulb:nth-child(3n+1) { animation-delay: 1.7s; }
    @keyframes tw { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
    @media (prefers-reduced-motion: reduce) { .bulb { animation: none; } }
    header { padding-block: 10px 6px; }
    .kicker { font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--sky); margin: 0; }
    /* Заголовок скромный: экран телефона — для событий, а не для шапки. */
    h1 { font-family: var(--display); font-weight: 800; font-size: clamp(1.5rem, 5vw, 2.1rem); line-height: 1.1; margin: 0; text-wrap: balance; }
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
    .tb-search { width: 36px; padding: 0; }
    .tb-search .ic { width: 18px; height: 18px; color: var(--text); }
    .tb-search[aria-expanded="true"] { background: var(--text); border-color: var(--text); } .tb-search[aria-expanded="true"] .ic { color: var(--night); }
    @media (max-width: 379px) { .tb-brand span { display: none; } }
    .tabs { display: flex; gap: 3px; padding: 3px; background: var(--card); border: 1px solid var(--line); border-radius: 999px; }
    .tabs a { display: inline-flex; align-items: center; gap: 5px; min-height: 34px; box-sizing: border-box; padding: 7px 10px; border-radius: 999px; color: var(--muted); font: 600 .86rem var(--body); text-decoration: none; white-space: nowrap; }
    @media (min-width: 640px) { .tabs a { padding: 7px 13px; font-size: .9rem; } }
    .tabs a .ic { width: 16px; height: 16px; color: var(--c, var(--sky)); }
    @media (max-width: 419px) { .tabs a .ic { display: none; } }  /* на узком телефоне — только слова, чтобы название не прижималось */
    .tabs a:hover { color: var(--text); }
    .tabs a[aria-current] { background: var(--text); color: var(--night); }
    .tabs a[aria-current] .ic { color: inherit; }
    .tb-brand:focus-visible, .tabs a:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }
    .xbanner { display: flex; align-items: center; gap: 12px; margin: 26px 0 0; padding: 12px 16px; border-radius: 16px; text-decoration: none; color: var(--text);
      background: linear-gradient(100deg, #17284a, #0f1a30); border: 1px solid #2b3f66; }
    .xbanner[hidden] { display: none; }
    .xbanner .ic { flex: none; width: 28px; height: 28px; color: #6fe3a5; }
    .xbanner.to-afisha .ic { color: var(--sky); }
    .xbanner b { display: block; font-family: var(--display); font-weight: 700; font-size: 1rem; }
    .xbanner small { display: block; color: var(--muted); font-size: .86rem; }
    @media (max-width: 479px) { .xbanner { padding: 10px 14px; } .xbanner small { display: none; } .xbanner .ic { width: 24px; height: 24px; } }
    .xbanner .go { margin-left: auto; color: var(--warm); font-size: 1.3rem; }
    .xbanner:hover { border-color: #3d5689; }
    .fnav { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 4px; }
    .fnav a { color: var(--sky); text-underline-offset: 3px; } .fnav span { color: var(--text); }
  
    /* Фильтры — как на больших афишах: поиск, лента дней на две недели, ряд видов кнопками, район и переключатели.
       Всё видно сразу; выпадающий список остался только у района — районов мало, и его меняют реже всего. */
    .fbar { position: sticky; top: calc(env(safe-area-inset-top, 0px) + var(--tbh, 60px)); z-index: 11; display: grid; gap: 8px; padding-block: 10px; background: var(--night);
      margin-inline: calc(-1 * var(--gutter)); padding-inline: var(--gutter); border-bottom: 1px solid transparent; }
    .fbar.stuck { border-bottom-color: var(--line); box-shadow: 0 10px 18px -14px rgba(0, 0, 0, .8); }
    .fbar .strip { margin-inline: calc(-1 * var(--gutter)); padding-inline: var(--gutter); }
    .sep { flex: none; width: 1px; align-self: stretch; margin: 6px 2px; background: var(--line); }
    .search { position: relative; display: flex; align-items: center; }
    .search[hidden] { display: none; }
    .search .ic { position: absolute; left: 14px; width: 18px; height: 18px; color: var(--muted); pointer-events: none; }
    .search input { width: 100%; box-sizing: border-box; min-height: 44px; padding: 10px 44px 10px 42px; border-radius: 999px; border: 1px solid var(--line);
      background: var(--card); color: var(--text); font: 500 16px var(--body); -webkit-appearance: none; appearance: none; }
    .search input::placeholder { color: var(--muted); }
    .search input:focus { outline: 2px solid var(--warm); outline-offset: 1px; }
    .search input::-webkit-search-cancel-button { display: none; }
    .q-clear { position: absolute; right: 6px; width: 34px; height: 34px; border-radius: 999px; border: 0; background: transparent; color: var(--muted); font-size: 1.3rem; line-height: 1; cursor: pointer; }
    .q-clear[hidden] { display: none; }
    /* Ленты на телефоне прокручиваются вбок и уходят под край экрана — так видно, что дальше есть ещё. */
    .strip { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin-inline: calc(-1 * var(--gutter)); padding-inline: var(--gutter); scroll-padding-inline: var(--gutter); }
    .strip::-webkit-scrollbar { display: none; }
    @media (min-width: 1272px) { .strip { margin-inline: 0; padding-inline: 0; } }
    /* На компьютере прокрутка вбок неудобна — дни и виды переносятся на следующую строку. */
    @media (min-width: 900px) { .fbar .strip { flex-wrap: wrap; overflow: visible; margin-inline: 0; padding-inline: 0; gap: 5px; } .chip { padding-inline: 9px; } .tb-search { padding: 0; } .sep { margin-inline: 1px; } }
    .chip { flex: none; position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 36px; box-sizing: border-box; padding: 6px 12px;
      border-radius: 999px; border: 1px solid var(--line); background: var(--card); color: var(--text); font: 600 .86rem var(--body); white-space: nowrap; cursor: pointer; }
    .chip.x { color: var(--sky); background: transparent; }
    .chip.x[hidden] { display: none; }
    .chip:hover { border-color: #3a4d74; }
    .chip .ic { width: 17px; height: 17px; color: var(--c, var(--sky)); }
    .chip[aria-pressed="true"] { background: var(--c, var(--text)); border-color: var(--c, var(--text)); color: var(--night); }
    .chip[aria-pressed="true"] .ic { color: inherit; }
    .chip:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }
    /* День в ленте одной строкой: «Сегодня», «Завтра», «пн 23»; выходные — тёплым. */
    .day { font-variant-numeric: tabular-nums; }
    .day small { font-weight: 500; color: var(--muted); margin-right: 1px; }
    .day.we small { color: var(--warm); }
    @media (min-width: 900px) { .day.far { display: none; } }  /* на компьютере 9 дней в одну строку, дальше — «Другая дата» */
    .day[aria-pressed="true"] small { color: inherit; }
    .chip.tg[aria-pressed="true"] { --c: var(--ok); }
    .chip.tg.ru[aria-pressed="true"] { --c: var(--sky); }
    .row2 { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
    .pick { gap: 4px; padding-right: 9px; }
    .pick:hover { border-color: #3a4d74; }
    .pick select { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; font-size: 16px; border: 0; appearance: none; }
    .pick .chev { flex: none; width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; opacity: .7; }
    .pick .ic { width: 17px; height: 17px; color: var(--sky); }
    .pick.on { background: var(--text); border-color: var(--text); color: var(--night); } .pick.on .ic { color: inherit; }
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
  
    /* Заголовок над списком: что показано и сколько. */
    .lhead { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 26px 0 12px; }
    .lhead h2 { font-family: var(--display); font-weight: 700; font-size: 1.12rem; line-height: 1.2; margin: 0; }
    .lhead span { flex: none; color: var(--muted); font-size: .88rem; font-variant-numeric: tabular-nums; }
    /* «Главное» — первый приоритет из таблицы недели: крупные карточки лентой (на компьютере — сеткой по три). */
    .picks[hidden] { display: none; }
    .picks .strip { gap: 10px; padding-bottom: 2px; scroll-snap-type: x mandatory; }
    .pc { flex: none; width: min(80vw, 300px); scroll-snap-align: start; box-sizing: border-box; display: flex; flex-direction: column; gap: 9px; padding: 16px 16px 15px;
      border-radius: 18px; color: inherit; text-decoration: none;
      background: linear-gradient(165deg, color-mix(in srgb, var(--c) 28%, var(--night)), color-mix(in srgb, var(--c) 9%, var(--night)) 72%);
      border: 1px solid color-mix(in srgb, var(--c) 52%, var(--night)); transition: border-color .15s; }
    .pc[hidden] { display: none; }
    .pc:hover { border-color: var(--c); }
    .pc-title { font-family: var(--display); font-weight: 700; font-size: 1.04rem; line-height: 1.28; text-wrap: balance; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .pc-why { color: #cfdae7; font-size: .88rem; line-height: 1.42; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .pc-foot { margin-top: auto; display: grid; gap: 2px; padding-top: 4px; }
    @media (min-width: 900px) { .picks .strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: visible; margin-inline: 0; padding-inline: 0; } .pc { width: auto; } }
    .ev-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
    .tag { font-size: .72rem; font-weight: 700; line-height: 1.5; padding: 1px 7px; border-radius: 999px; background: color-mix(in srgb, var(--ok) 15%, transparent); color: var(--ok); }
    .tag.ru { background: color-mix(in srgb, var(--sky) 15%, transparent); color: var(--sky); }
    #list { margin-top: 0; }
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
    /* Переносы с дефисом нужны только в узкой колонке телефона; на компьютере слова целиком. */
    @media (min-width: 640px) { .ev-title { font-size: 1rem; hyphens: manual; overflow-wrap: break-word; } }
    .ev-meta { display: grid; gap: 3px; min-width: 0; }
    .ev-meta > span { overflow-wrap: anywhere; }
    .ic { flex: none; width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
    .ev-type { display: flex; align-items: center; gap: 6px; font-size: .82rem; font-weight: 700; color: var(--c); }
    .ev-type .ic { width: 20px; height: 20px; }
    .ev-date { font-size: .88rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .ev-city { font-size: .86rem; color: var(--muted); }
    .xbanner:focus-visible, .fnav a:focus-visible, .ev:focus-visible, .pc:focus-visible, .s-rel a:focus-visible, .clear:focus-visible, .more:focus-visible, .empty button:focus-visible, .sheet button:focus-visible, .sheet a:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; }
  
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
    .s-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
    .s-map { display: inline-flex; align-items: center; gap: 8px; padding: 11px 18px; border-radius: 999px; background: var(--warm); color: #1c1300; font-weight: 700; text-decoration: none; }
    .s-btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 999px; border: 1px solid var(--line); background: transparent; color: var(--text); font: 600 .92rem var(--body); cursor: pointer; }
    .s-btn:hover { border-color: #3a4d74; background: var(--card-hi); }
    .s-btn .ic { width: 18px; height: 18px; }
    .s-btn[hidden], .s-map[hidden] { display: none; }
    /* «В эти дни рядом» — чтобы из карточки можно было перейти к соседнему событию, не возвращаясь к списку. */
    .s-rel { display: grid; gap: 2px; margin-top: 6px; padding-top: 14px; border-top: 1px solid var(--line); }
    .s-rel[hidden] { display: none; }
    .s-rel h3 { margin: 0 0 6px; font-size: .76rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
    .s-rel a { display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 2px 10px; align-items: start; padding: 8px 0; color: var(--text); text-decoration: none; }
    .s-rel a .ic { width: 20px; height: 20px; color: var(--c); margin-top: 1px; }
    .s-rel a b { font-weight: 600; } .s-rel a small { grid-column: 2; color: var(--muted); font-size: .86rem; }
    .s-rel a:hover b { text-decoration: underline; text-underline-offset: 3px; }
    .toast { position: fixed; left: 50%; bottom: calc(22px + env(safe-area-inset-bottom, 0px)); transform: translateX(-50%); z-index: 30; padding: 10px 18px; border-radius: 999px;
      background: var(--text); color: var(--night); font-weight: 600; box-shadow: 0 10px 30px rgba(0, 0, 0, .45); }
    .toast[hidden] { display: none; }
  
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
  <main>
  ${cfg.garland ? GARLAND : ''}  <header>
      <h1>${cfg.h1}</h1>
    </header>
    <!-- Фильтры: две строки, прилипают под верхней полосой. Дни; район, «Бесплатно», «На русском» и виды. Поиск — по значку лупы. -->
    <div class="fbar" id="fbar" role="group" aria-label="Фильтры">
      <div class="search" id="searchrow" hidden>${svg('search')}<input id="f-q" type="search" placeholder="Название, место или город" autocomplete="off" enterkeyhint="search" aria-label="Поиск по афише"><button type="button" class="q-clear" id="q-clear" aria-label="Очистить поиск" hidden>×</button></div>
      <div class="strip" id="days" role="group" aria-label="Когда"><button type="button" class="chip tb-search" id="tb-search" aria-label="Поиск" aria-expanded="false" aria-controls="searchrow">${svg('search')}</button></div>
      <div class="strip" id="opts" role="group" aria-label="Где и что">
        <button type="button" class="chip x" id="clear" aria-label="Сбросить фильтры" hidden>× Сбросить</button>
        <label class="chip pick">${svg('pin')}<span class="pick-t">Весь Кипр</span>${CHEV}<select id="f-reg" aria-label="Где"><option value="">Весь Кипр</option>${regions.map((r) => `<option value="${esc(r)}">${esc(r)}</option>`).join('')}</select></label>${toggles.free ? `
        <button type="button" class="chip tg" id="f-free" aria-pressed="false">Бесплатно</button>` : ''}${toggles.ru ? `
        <button type="button" class="chip tg ru" id="f-ru" aria-pressed="false">На русском</button>` : ''}
        <span class="sep" aria-hidden="true"></span>${kinds.map((k) => `
        <button type="button" class="chip" data-k="${k.t}" data-kind="${k.t}" aria-pressed="false">${svg(k.icon)}${esc(k.label)}</button>`).join('')}
      </div>
      <div class="cal" id="cal" role="dialog" aria-label="Выберите дату" hidden>
        <div class="cal-h"><button type="button" class="cal-nav" id="cal-prev" aria-label="Предыдущий месяц">‹</button><b id="cal-m"></b><button type="button" class="cal-nav" id="cal-next" aria-label="Следующий месяц">›</button></div>
        <div class="cal-g" id="cal-g"></div>
      </div>
    </div>

    <section class="picks" id="picks" aria-labelledby="picks-h" hidden>
      <div class="lhead"><h2 id="picks-h">Главное</h2><span id="picks-when"></span></div>
      <div class="strip" id="pcs">${list.filter((e) => (e.priority ?? 3) === 1).map(pickCard).join('')}
      </div>
    </section>

  ${cfg.banner ? cfg.banner(artifact) : ''}
    <div class="lhead"><h2 id="list-h">Все события</h2><span id="count" aria-live="polite"></span></div>
    <div id="list">
      <ul class="evs" id="evs">${list.map(card).join('')}
      </ul>
      <button type="button" class="more" id="more" hidden></button>
      <p class="empty" id="empty" hidden>Ничего не нашлось. <button type="button" id="reset">Сбросить фильтры</button></p>
    </div>

  </main>
    <footer>
      <span class="brand"><svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">${MARK}</svg>${esc(SITE_NAME)}</span>
      <span>${esc(SITE_NAME)} — гид по Кипру на русском: что происходит, куда сходить и к кому обратиться.</span>${artifact ? '' : `
      <nav class="fnav" aria-label="Разделы сайта">${PAGES.map((p) => p === cfg ? `<span>${esc(p.nav)}</span>` : `<a href="${p.path}">${esc(p.nav)}</a>`).join('')}</nav>`}
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
      <div class="s-actions">
        <a class="s-map" id="s-map" href="#" target="_blank" rel="noopener">Открыть на карте ↗</a>
        <button type="button" class="s-btn" id="s-share">${svg('share')}Поделиться</button>${artifact ? '' : `
        <button type="button" class="s-btn" id="s-cal">${svg('plus')}В календарь</button>`}
      </div>
      <div class="s-rel" id="s-rel" hidden></div>
    </div>
  </div>
  <div class="toast" id="toast" role="status" hidden></div>${artifact ? '' : `
  <script type="application/ld+json">${jsonLd(list, cfg)}</script>`}
  
  <script>
    (function () {
      var DATA = ${JSON.stringify(detail)};
      var MON = ${JSON.stringify(MON_FULL)}, MON_S = ${JSON.stringify(MON)}, WD = ${JSON.stringify(WD)};
      var ICONS = ${JSON.stringify(Object.fromEntries(Object.keys(ICONS).map((k) => [k, svg(k)])))}, KIND_ICON = ${JSON.stringify(Object.fromEntries(cfg.kinds.map((k) => [k.t, k.icon])))};
      var SHARE = ${JSON.stringify(SITE_URL + cfg.path)};
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
      var fbar = el('fbar');
      var setTb = function () { if (bar) document.documentElement.style.setProperty('--tbh', bar.offsetHeight + 'px'); };
      setTb(); window.addEventListener('resize', setTb);
      if (bar) { var onScroll = function () { bar.classList.toggle('stuck', window.scrollY > 4); if (fbar) fbar.classList.toggle('stuck', fbar.getBoundingClientRect().top <= bar.offsetHeight + 1 && window.scrollY > 4); }; window.addEventListener('scroll', onScroll, { passive: true }); onScroll(); }
      all('.tabs a[aria-current]').forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }); });
      // Прошедшее убираем; баннер Рождества — до конца сезона.
      all('.xbanner').forEach(function (b) { if (b.dataset.until < today) b.hidden = true; });
      all('#evs > li, .pc').forEach(function (n) { if (n.dataset.end < today) n.remove(); });
      var items = all('#evs > li'), list = el('evs'), pcs = all('.pc'), byId = {};
      items.forEach(function (li) { byId[li.dataset.id] = li; });

      var shortD = function (iso) { return d(iso).getUTCDate() + ' ' + MON_S[d(iso).getUTCMonth()]; };
      var dayLabel = function (iso) { return WD[d(iso).getUTCDay()] + ', ' + shortD(iso); };
      var span = function (a) {
        var x = a[0], y = a[a.length - 1];
        if (x === y) return dayLabel(x);
        return d(x).getUTCMonth() === d(y).getUTCMonth() ? d(x).getUTCDate() + '–' + shortD(y) : shortD(x) + ' – ' + shortD(y);
      };
      var plural = function (n, one, few, many) { var a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many; };
      // Ближайшие выходные начиная с дня iso; в воскресенье — только оно.
      var weekend = function (iso) { var wd = d(iso).getUTCDay(); if (wd === 0) return [iso]; var sat = plus(iso, 6 - wd); return [sat, plus(sat, 1)]; };
      var seasonEnd = items.reduce(function (m, li) { return li.dataset.end > m ? li.dataset.end : m; }, today);
      var we1 = weekend(today);

      // Даты на плитках словами, как на больших афишах: «Сегодня, 20:00», «Завтра», «сб, 28 ноя, 19:30»;
      // у долгого события, которое уже идёт, — «до 17 янв».
      var whenLabel = function (x) {
        if (x.long) return x.start > today ? null : x.end === today ? 'Последний день' : 'до ' + shortD(x.end);
        return (x.start === today ? 'Сегодня' : x.start === tomorrow ? 'Завтра' : dayLabel(x.start)) + (x.time ? ', ' + x.time : '');
      };
      items.concat(pcs).forEach(function (n) { var w = whenLabel(n.dataset), t = n.querySelector('.ev-date'); if (w && t) t.textContent = w; });

      // «Когда» — лента дней на две недели вперёд (как у Яндекс Афиши): все дни, выходные, каждый день, другая дата из календаря.
      var daysEl = el('days'), MONTH0 = today.slice(5, 7);
      var chip = function (v, html, cls, label) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'chip' + (cls ? ' ' + cls : ''); b.dataset.v = v;
        b.setAttribute('aria-pressed', 'false'); b.innerHTML = html; if (label) b.setAttribute('aria-label', label); daysEl.appendChild(b); return b;
      };
      chip('', 'Все дни');
      if (we1[0] <= seasonEnd) chip('we', 'Выходные', '', 'Выходные, ' + span(we1));
      var PERIODS = { we: we1 };
      for (var i = 0; i < 14; i++) {
        var iso = plus(today, i); if (iso > seasonEnd) break;
        var wd = d(iso).getUTCDay(), num = d(iso).getUTCDate() + (iso.slice(5, 7) !== MONTH0 && (d(iso).getUTCDate() === 1 || i === 0) ? ' ' + MON_S[d(iso).getUTCMonth()] : '');
        var lab = i === 0 ? 'Сегодня' : i === 1 ? 'Завтра' : '<small>' + WD[wd] + '</small> ' + num;
        chip('d:' + iso, lab, 'day' + (wd === 0 || wd === 6 ? ' we' : '') + (i >= 9 ? ' far' : ''), dayLabel(iso));
        PERIODS['d:' + iso] = [iso];
      }
      var other = chip('pick', ICONS.calendar + '<span>Другая дата</span>');

      var state = { v: '', days: null, reg: '', kind: '', q: '', free: false, ru: false }, shown = 0;
      var openOn = function (n, x) { return n.dataset.days ? n.dataset.days.split(' ').indexOf(x) >= 0 : n.dataset.start <= x && x <= n.dataset.end; };
      var match = function (n, s) {
        if (s.kind && n.dataset.kind !== s.kind) return false;
        if (s.reg && n.dataset.reg.split('|').indexOf(s.reg) < 0) return false;
        if (s.free && !n.dataset.free) return false;
        if (s.ru && !n.dataset.ru) return false;
        if (s.q && !s.q.split(' ').every(function (w) { return n.dataset.q.indexOf(w) >= 0; })) return false;
        // Однодневное — если оно в один из выбранных дней; долгое — если в один из них открыто (у деревень — дни из open_days).
        if (s.days) return s.days.some(function (x) { return n.dataset.long ? openOn(n, x) : n.dataset.start === x; });
        return true;
      };
      var regSel = el('f-reg');
      // Районы без событий (после того как прошедшее убрано) не показываем.
      all('#f-reg option').forEach(function (o) { if (o.value && !items.some(function (li) { return li.dataset.reg.split('|').indexOf(o.value) >= 0; })) o.remove(); });
      var any = function () { return !!(state.v || state.reg || state.kind || state.q || state.free || state.ru); };
      function sync() {
        all('#days .chip[data-v]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.v === state.v || (b === other && state.v.indexOf('x:') === 0))); });
        all('#opts .chip[data-k]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.k === state.kind)); });
        var pl = regSel.parentNode; pl.querySelector('.pick-t').textContent = regSel.value || 'Весь Кипр'; pl.classList.toggle('on', !!regSel.value);
        if (el('f-free')) el('f-free').setAttribute('aria-pressed', String(state.free));
        if (el('f-ru')) el('f-ru').setAttribute('aria-pressed', String(state.ru));
        el('q-clear').hidden = !el('f-q').value;
        el('clear').hidden = !any();
      }

      // Все плитки одной высоты: по самой высокой видимой.
      var equalize = function () {
        var tiles = all('#list .ev');
        tiles.forEach(function (t) { t.style.minHeight = ''; });
        var h = 0;
        tiles.forEach(function (t) { if (t.offsetParent) h = Math.max(h, t.getBoundingClientRect().height); });
        if (h) tiles.forEach(function (t) { t.style.minHeight = Math.ceil(h) + 'px'; });
      };
      // Порядок: сначала приоритет из рабочей таблицы недели (1 — в первую очередь, 2 — интересно, 3 — дополнительно, DEC-W45),
      // внутри приоритета — ближайшее. Уже идущее стоит как «сегодня» или как выбранный день;
      // в один день — сначала однодневные по времени, потом долгие.
      var effDay = function (n) {
        var from = state.days ? state.days[0] : today, eff = n.dataset.start < from ? from : n.dataset.start;
        if (n.dataset.days) eff = n.dataset.days.split(' ').filter(function (x) { return x >= from; })[0] || n.dataset.end;
        return eff;
      };
      var dateKey = function (n) { return effDay(n) + (n.dataset.long ? '1' : '0') + (n.dataset.time || '00:00') + n.dataset.start; };
      var sortKey = function (n) { return (n.dataset.prio || '3') + dateKey(n); };
      var wide = function () { return matchMedia('(min-width: 900px)').matches; };
      // Сколько плиток видно до «Показать ещё»: 6 рядов на телефоне, 4 на компьютере; кнопка добавляет столько же.
      var page = function () { return wide() ? 16 : 12; };
      var periodText = function () {
        if (!state.days) return 'на ближайшую неделю';
        if (state.v === 'we') return 'на выходные';
        return state.days[0] === today ? 'на сегодня' : state.days[0] === tomorrow ? 'на завтра' : 'на ' + dayLabel(state.days[0]);
      };
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
        el('list-h').textContent = any() ? 'Нашлось' : 'Все события';
        el('count').textContent = vis.length + ' ' + plural(vis.length, 'событие', 'события', 'событий');
        // «Главное»: первый приоритет по тем же фильтрам, ближайшее первым; без выбранного дня — на неделю вперёд.
        // Если событий и так мало, подборка только повторила бы список — тогда её нет.
        if (!keep) {
          var horizon = plus(today, 7);
          var top = pcs.filter(function (n) { return match(n, state) && (state.days || effDay(n) <= horizon); })
            .sort(function (a, b) { var x = dateKey(a), y = dateKey(b); return x < y ? -1 : x > y ? 1 : 0; });
          var cap = wide() ? 6 : 10, showPicks = vis.length > 12 && top.length >= 3 && !state.q;
          pcs.forEach(function (n) { n.hidden = true; });
          top.forEach(function (n, i) { n.hidden = i >= cap; el('pcs').appendChild(n); });
          el('picks').hidden = !showPicks;
          el('picks-when').textContent = periodText();
          el('pcs').scrollLeft = 0;
        }
        equalize();
      }
      // После смены фильтра результат должен быть виден: если начало результатов выше полосы фильтров или далеко внизу — прокручиваем к нему.
      var reveal = function () {
        var fb = el('fbar').getBoundingClientRect().bottom, tgt = el('picks').hidden ? el('list-h').parentNode : el('picks');
        var y = tgt.getBoundingClientRect().top;
        if (y < fb || y > innerHeight * 0.62) window.scrollTo({ top: window.scrollY + y - fb - 8, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      };
      var apply = function () { sync(); render(); reveal(); };
      var setDays = function (v, days) { state.v = v; state.days = days; closeCal(); apply(); };
      daysEl.addEventListener('click', function (e) {
        var b = e.target.closest('.chip'); if (!b || b.id === 'tb-search') return;
        if (b === other) { if (cal.hidden) openCal(); else closeCal(); return; }
        setDays(b.dataset.v, b.dataset.v ? PERIODS[b.dataset.v] : null);
      });
      el('opts').addEventListener('click', function (e) {
        var b = e.target.closest('.chip[data-k]'); if (!b) return;
        state.kind = b.dataset.k === state.kind ? '' : b.dataset.k; apply();
      });
      regSel.addEventListener('change', function () { state.reg = regSel.value; apply(); });
      ['free', 'ru'].forEach(function (k) {
        var b = el('f-' + k); if (b) b.addEventListener('click', function () { state[k] = !state[k]; apply(); });
      });
      var qIn = el('f-q'), qT = 0;
      var norm = function (v) { return v.toLowerCase().replace(/ё/g, 'е').replace(/\\s+/g, ' ').trim(); };
      qIn.addEventListener('input', function () { clearTimeout(qT); qT = setTimeout(function () { state.q = norm(qIn.value); sync(); render(); }, 120); });
      qIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') qIn.blur(); });
      el('q-clear').addEventListener('click', function () { qIn.value = ''; state.q = ''; sync(); render(); qIn.focus(); });
      var tbS = el('tb-search'), sRow = el('searchrow');
      tbS.addEventListener('click', function () {
        var open = sRow.hidden;
        if (!open && qIn.value) { qIn.focus(); return; }  // со словом в поиске строка остаётся, значок просто ставит курсор
        sRow.hidden = !open; tbS.setAttribute('aria-expanded', String(open));
        if (open) qIn.focus();  // строка поиска внутри прилипшей полосы — видна при любой прокрутке
      });

      // «Другая дата»: свой календарь в пределах сезона (с сегодняшнего дня до конца последнего события).
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
        var iso = b.dataset.d, inStrip = PERIODS['d:' + iso];
        // День из ленты — нажимаем его; дальше двух недель — подпись «Другой даты» меняется на выбранный день.
        other.querySelector('span').textContent = inStrip ? 'Другая дата' : dayLabel(iso);
        setDays(inStrip ? 'd:' + iso : 'x:' + iso, [iso]);
        var on = daysEl.querySelector('[aria-pressed="true"]'); if (on) { on.focus(); on.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
      });
      document.addEventListener('click', function (e) { if (!cal.hidden && !cal.contains(e.target) && !other.contains(e.target)) closeCal(); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !cal.hidden) { closeCal(); other.focus(); } });
      el('more').addEventListener('click', function () { shown += page(); render(true); });
      function resetAll() {
        state = { v: '', days: null, reg: '', kind: '', q: '', free: false, ru: false };
        regSel.value = ''; qIn.value = ''; other.querySelector('span').textContent = 'Другая дата'; sRow.hidden = true; tbS.setAttribute('aria-expanded', 'false');
        closeCal(); sync(); render();
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
      var shade = el('shade'), last = null, cur = null, keepY = null;
      var toastT = 0;
      var toast = function (t) { var x = el('toast'); x.textContent = t; x.hidden = false; clearTimeout(toastT); toastT = setTimeout(function () { x.hidden = true; }, 2200); };
      // «В эти дни рядом»: до четырёх событий в том же районе в тот же день (у долгого — сегодня или выбранный день).
      function related(id) {
        var me = byId[id]; if (!me) return [];
        var reg = me.dataset.reg.split('|')[0], x = DATA[id];
        var dayOf = me.dataset.long ? (state.days ? state.days[0] : (x.start > today ? x.start : today)) : x.start;
        return items.filter(function (n) {
          return n !== me && reg && n.dataset.reg.split('|').indexOf(reg) >= 0 && (n.dataset.long ? openOn(n, dayOf) : n.dataset.start === dayOf);
        }).sort(function (a, b) { var p = sortKey(a), q = sortKey(b); return p < q ? -1 : p > q ? 1 : 0; }).slice(0, 4).map(function (n) { return { id: n.dataset.id, day: dayOf, reg: reg }; });
      }
      function show() {
        var id = location.hash.slice(1), x = DATA[id];
        if (!x) { cur = null; shade.hidden = true; document.body.classList.remove('locked'); if (keepY !== null) { window.scrollTo(0, keepY); keepY = null; } if (last) { last.focus({ preventScroll: true }); last = null; } return; }
        if (shade.hidden) keepY = window.scrollY;
        cur = id;
        el('sheet').dataset.kind = x.group; el('s-kind').innerHTML = ICONS[x.icon]; el('s-kind').appendChild(document.createTextNode(x.kind));
        el('s-title').textContent = x.title;
        el('s-orig').textContent = x.orig; el('s-orig').hidden = !x.orig;
        var st = status(x), s = el('s-status');
        s.hidden = !st; if (st) { s.textContent = st.text; s.classList.toggle('now', st.now); }
        var f = el('s-facts'); f.innerHTML = '';
        x.facts.forEach(function (p) {
          var row = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd');
          dt.textContent = p[0]; dd.textContent = p[1]; row.appendChild(dt); row.appendChild(dd); f.appendChild(row);
        });
        el('s-summary').textContent = x.summary; el('s-summary').hidden = !x.summary;
        var m = el('s-map'); m.hidden = !x.map; if (x.map) m.href = x.map;
        var rel = related(id), r = el('s-rel');
        r.innerHTML = ''; r.hidden = !rel.length;
        if (rel.length) {
          var h = document.createElement('h3'); h.textContent = 'Ещё ' + (rel[0].day === today ? 'сегодня' : rel[0].day === tomorrow ? 'завтра' : dayLabel(rel[0].day)) + ' · ' + rel[0].reg; r.appendChild(h);
          rel.forEach(function (o) {
            var y = DATA[o.id], a = document.createElement('a'); a.href = '#' + o.id; a.dataset.kind = y.group;
            a.innerHTML = ICONS[y.icon]; var b = document.createElement('b'); b.textContent = y.title; a.appendChild(b);
            var sm = document.createElement('small'); sm.textContent = y.kind + (y.time && y.start === y.end ? ' · ' + y.time : ''); a.appendChild(sm);
            r.appendChild(a);
          });
        }
        shade.hidden = false; el('sheet').scrollTop = 0; document.body.classList.add('locked'); el('s-close').focus();
      }
      // «Поделиться»: системное меню, где оно есть; иначе ссылка копируется. Ссылка всегда на страницу сайта.
      el('s-share').addEventListener('click', function () {
        if (!cur) return;
        var url = SHARE + '#' + cur, title = DATA[cur].title;
        var copy = function () {
          if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(function () { toast('Ссылка скопирована'); }, function () { toast(url); });
          else toast(url);
        };
        if (navigator.share) navigator.share({ title: title, url: url }).catch(function (e) { if (!e || e.name !== 'AbortError') copy(); });
        else copy();
      });
${artifact ? '' : `      // «В календарь»: файл .ics — его открывают календари iPhone, Android и Outlook.
      var pad = function (n) { return (n < 10 ? '0' : '') + n; };
      var icsEsc = function (t) { return String(t).replace(/\\\\/g, '\\\\\\\\').replace(/[,;]/g, function (c) { return '\\\\' + c; }).replace(/\\n/g, '\\\\n'); };
      if (el('s-cal')) el('s-cal').addEventListener('click', function () {
        if (!cur) return;
        var x = DATA[cur], ymd = function (iso) { return iso.replace(/-/g, ''); }, lines;
        if (x.time && x.start === x.end) {
          var t = x.time.split(':'), e2 = x.endTime ? x.endTime.split(':') : [String((+t[0] + 2) % 24), t[1]];
          var endDay = x.endTime || +t[0] < 22 ? x.start : plus(x.start, 1);
          lines = ['DTSTART;TZID=Europe/Nicosia:' + ymd(x.start) + 'T' + pad(+t[0]) + t[1] + '00', 'DTEND;TZID=Europe/Nicosia:' + ymd(endDay) + 'T' + pad(+e2[0]) + e2[1] + '00'];
        } else lines = ['DTSTART;VALUE=DATE:' + ymd(x.start), 'DTEND;VALUE=DATE:' + ymd(plus(x.end, 1))];
        var now = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
        var ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//City Compas//RU', 'BEGIN:VEVENT', 'UID:' + cur + '@citycompas.com', 'DTSTAMP:' + now].concat(lines,
          ['SUMMARY:' + icsEsc(x.title), 'LOCATION:' + icsEsc(x.place + ', Cyprus'), 'DESCRIPTION:' + icsEsc(x.summary.slice(0, 500) + '\\n\\n' + SHARE + '#' + cur), 'URL:' + SHARE + '#' + cur, 'END:VEVENT', 'END:VCALENDAR']).join('\\r\\n');
        var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([ics], { type: 'text/calendar;charset=utf-8' })); a.download = cur + '.ics';
        document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      });
`}      function close() {
        if (history.length > 1 && last) history.back(); else { location.hash = ''; }
      }
      document.addEventListener('click', function (e) { var a = e.target.closest('.ev, .pc'); if (a) last = a; });
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
