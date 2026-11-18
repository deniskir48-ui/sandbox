#!/usr/bin/env node
/**
 * Отдельная страница «Рождество на Кипре» — одним файлом, без остального сайта (DEC-W38).
 *   node scripts/build-christmas-standalone.mjs        → standalone/christmas.html
 * Данные — те же события Афиши с метками christmas-* (scripts/import-christmas.py), только status: published.
 * Ссылки ведут на источники событий и карты, а не на страницы сайта (сайт пока не опубликован).
 * Прошедшее скрывается в браузере по дате на Кипре; статус парков («работает до», «откроется») считается там же.
 */
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'yaml';

const DIR = path.resolve('src/content/events');
const OUT = path.resolve('standalone/christmas.html');
const MON = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const MON_FULL = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const KINDS = [
  ['christmas-villages', 'Рождественские деревни'],
  ['christmas-lights', 'Ёлки и огни'],
  ['christmas-markets', 'Ярмарки'],
  ['christmas-other', 'Мастер-классы и другое'],
];

const esc = (s = '') => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const day = (iso) => new Date(iso + 'T12:00:00Z');
const short = (iso) => `${day(iso).getUTCDate()} ${MON[day(iso).getUTCMonth()]}`;
const full = (iso) => `${day(iso).getUTCDate()} ${MON_FULL[day(iso).getUTCMonth()]}`;
const map = (q) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;

const events = fs.readdirSync(DIR).filter((f) => f.endsWith('.yaml'))
  .map((f) => parse(fs.readFileSync(path.join(DIR, f), 'utf8')))
  .filter((e) => e?.status === 'published' && (e.tags ?? []).includes('christmas'));
const key = (e) => `${e.date}T${e.time ?? '00:00'}`;
const parks = events.filter((e) => e.tags.includes('christmas-parks')).sort((a, b) => key(a).localeCompare(key(b)));
const week = events.filter((e) => !e.tags.includes('christmas-parks')).sort((a, b) => key(a).localeCompare(key(b)));
const kindOf = (e) => (KINDS.find(([t]) => e.tags.includes(t)) ?? KINDS[3])[0];
const kinds = KINDS.map(([t, label]) => ({ t, label, n: week.filter((e) => kindOf(e) === t).length })).filter((k) => k.n);
const updated = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'Europe/Nicosia' }).format(new Date());

const parkCard = (e) => {
  const end = e.end_date ?? e.date;
  const open = (e.hours ?? '').match(/\d{1,2}:\d{2}/)?.[0] ?? '';
  return `
    <li class="park" data-start="${e.date}" data-end="${end}" data-time="${open}">
      <div class="row"><span class="place">${esc(e.city)}${e.venue ? ` · ${esc(e.venue)}` : ''}</span><span class="status"></span></div>
      <h3>${esc(e.title)}</h3>
      <p class="when">${full(e.date)} — ${full(end)}</p>
      ${e.summary ? `<p class="desc">${esc(e.summary)}</p>` : ''}
      <dl class="facts">
        ${e.hours ? `<div><dt>Часы</dt><dd>${esc(e.hours)}</dd></div>` : ''}
        ${e.price ? `<div><dt>Стоимость</dt><dd>${esc(e.price)}</dd></div>` : ''}
      </dl>
      <div class="links">
        ${e.ticket_url ? `<a href="${esc(e.ticket_url)}" target="_blank" rel="noopener">Источник ↗</a>` : ''}
        <a href="${esc(map(`${e.venue ?? e.title} ${e.city}`))}" target="_blank" rel="noopener">На карте ↗</a>
      </div>
    </li>`;
};

const eventRow = (e) => {
  const end = e.end_date ?? e.date;
  const range = end !== e.date;
  const stubDay = range ? `${day(e.date).getUTCDate()}–${day(end).getUTCDate()}` : `${day(e.date).getUTCDate()}`;
  const stubSub = range ? `${WD[day(e.date).getUTCDay()]}–${WD[day(end).getUTCDay()]}` : WD[day(e.date).getUTCDay()];
  const meta = [e.time ? `в ${e.time}` : '', e.price ?? ''].filter(Boolean).join(' · ');
  return `
    <li class="ev" data-kind="${kindOf(e)}" data-end="${end}">
      <div class="stub" aria-hidden="true"><b>${stubDay}</b><span>${MON[day(e.date).getUTCMonth()]}</span><i>${stubSub}</i></div>
      <div class="ev-body">
        <h3>${esc(e.title)}</h3>
        <p class="ev-place">${esc(e.city)}${e.venue ? ` · ${esc(e.venue)}` : ''}${meta ? ` · ${esc(meta)}` : ''}</p>
        ${e.summary ? `<p class="ev-desc">${esc(e.summary)}</p>` : ''}
        ${e.ticket_url ? `<a class="more" href="${esc(e.ticket_url)}" target="_blank" rel="noopener">Подробнее ↗</a>` : ''}
      </div>
    </li>`;
};

const html = `<title>Рождество на Кипре</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Рождественские парки Кипра и праздники ближайших дней: ёлки, деревни, ярмарки.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Unbounded:wght@600;700;800&display=swap">
<style>
  /* Вечерний Кипр в декабре: ночное небо, гирлянда, голубой и оранжевый «Гида по Кипру». Сознательно одна тёмная тема. */
  :root {
    color-scheme: dark;
    --night: #0a1120; --card: #111a2e; --line: #22304d; --text: #eef3f9; --muted: #9fb0c8;
    --sky: #9fd5f2; --sun: #f26b21; --warm: #ffd38a; --ok: #7ee2b8;
    --display: "Unbounded", "Onest", system-ui, sans-serif; --body: "Onest", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  html { background: var(--night); }
  body { background: var(--night); color: var(--text); font-family: var(--body); font-size: 16px; line-height: 1.55;
    padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 44px; }
  .wrap { max-width: 900px; margin: 0 auto; }
  a { color: var(--sky); }
  .garland { display: block; width: 100%; height: 50px; }
  .bulb { animation: tw 3.2s ease-in-out infinite; } .bulb:nth-child(3n) { animation-delay: .8s; } .bulb:nth-child(3n+1) { animation-delay: 1.7s; }
  @keyframes tw { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
  @media (prefers-reduced-motion: reduce) { .bulb { animation: none; } }
  header { padding-block: 6px 26px; }
  .kicker { font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--sky); margin: 0; }
  h1 { font-family: var(--display); font-weight: 800; font-size: clamp(2rem, 7.5vw, 3.4rem); line-height: 1.06; margin: 10px 0 14px; text-wrap: balance; }
  h1 em { font-style: normal; color: var(--warm); }
  .lead { color: var(--muted); max-width: 62ch; margin: 0; font-size: 1.05rem; }
  .counts { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 16px 0 0; color: var(--muted); }
  .counts b { color: var(--warm); font-variant-numeric: tabular-nums; }
  h2 { font-family: var(--display); font-weight: 700; font-size: 1.35rem; margin: 34px 0 14px; }

  .parks { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 330px), 1fr)); }
  .park { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 20px; display: flex; flex-direction: column; gap: 9px; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
  .place { font-size: .76rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--sky); }
  .status { font-size: .78rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: color-mix(in srgb, var(--sun) 20%, transparent); color: #ffb488; }
  .status:empty { display: none; }
  .status.now { background: color-mix(in srgb, var(--ok) 16%, transparent); color: var(--ok); }
  .park h3 { font-family: var(--display); font-weight: 600; font-size: 1.15rem; line-height: 1.25; margin: 0; text-wrap: balance; }
  .when { margin: 0; font-weight: 600; color: var(--warm); font-variant-numeric: tabular-nums; }
  .desc { margin: 0; color: #d6e0ec; }
  .facts { margin: 0; display: grid; gap: 4px; font-size: .9rem; }
  .facts div { display: grid; grid-template-columns: 86px 1fr; gap: 8px; }
  .facts dt { color: var(--muted); } .facts dd { margin: 0; }
  .links { margin-top: auto; padding-top: 4px; display: flex; flex-wrap: wrap; gap: 8px 18px; font-weight: 600; font-size: .92rem; }
  .links a { text-decoration: none; }

  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
  .chip { font: 600 .9rem var(--body); color: var(--text); background: transparent; border: 1px solid var(--line); border-radius: 999px; padding: 8px 14px; cursor: pointer; }
  .chip em { font-style: normal; color: var(--muted); font-weight: 500; }
  .chip[aria-pressed="true"] { background: var(--sky); border-color: var(--sky); color: #0a1120; }
  .chip[aria-pressed="true"] em { color: inherit; opacity: .7; }
  .chip:focus-visible, .links a:focus-visible, .more:focus-visible { outline: 2px solid var(--warm); outline-offset: 3px; border-radius: 6px; }
  .evs { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
  .ev { display: grid; grid-template-columns: 64px minmax(0, 1fr); background: var(--card); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }
  .stub { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; padding: 12px 4px; background: color-mix(in srgb, var(--sky) 14%, var(--card)); border-right: 1px dashed var(--line); text-align: center; }
  .stub b { font-family: var(--display); font-size: 1.05rem; line-height: 1.1; color: var(--text); font-variant-numeric: tabular-nums; }
  .stub span { font-size: .82rem; color: var(--sky); font-weight: 600; } .stub i { font-style: normal; font-size: .72rem; color: var(--muted); }
  .ev-body { padding: 14px 16px; display: grid; gap: 5px; min-width: 0; }
  .ev h3 { margin: 0; font-size: 1.02rem; line-height: 1.3; }
  .ev-place { margin: 0; font-size: .86rem; color: var(--muted); }
  .ev-desc { margin: 0; font-size: .93rem; color: #d6e0ec; }
  .more { justify-self: start; font-weight: 600; font-size: .9rem; text-decoration: none; }
  footer { margin-top: 30px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: .9rem; display: grid; gap: 8px; }
  .brand { display: inline-flex; align-items: center; gap: 8px; font-family: var(--display); font-weight: 600; color: var(--text); }
  @media (min-width: 640px) { .park { padding: 22px 24px; } .ev { grid-template-columns: 76px minmax(0, 1fr); } }
</style>

<div class="wrap">
  <svg class="garland" viewBox="0 0 800 50" preserveAspectRatio="none" aria-hidden="true">
    <path d="M0 8 Q100 42 200 14 T400 14 T600 14 T800 8" fill="none" stroke="#2a3a5c" stroke-width="2"/>
    ${[[40, 19, '#ffd38a'], [95, 28, '#9fd5f2'], [150, 26, '#f26b21'], [205, 15, '#ffd38a'], [260, 21, '#7ee2b8'], [315, 28, '#9fd5f2'], [365, 21, '#f26b21'], [415, 14, '#ffd38a'], [470, 22, '#9fd5f2'], [520, 28, '#7ee2b8'], [570, 21, '#f26b21'], [620, 14, '#ffd38a'], [675, 22, '#9fd5f2'], [725, 27, '#f26b21'], [775, 15, '#ffd38a']]
      .map(([x, y, c]) => `<circle class="bulb" cx="${x}" cy="${y}" r="4.5" fill="${c}"/>`).join('')}
  </svg>
  <header>
    <p class="kicker">Сезон 2026–2027</p>
    <h1>Рождество <em>на&nbsp;Кипре</em></h1>
    <p class="lead">Хэллоуинские тыквы ещё не везде убрали, а Санта-Клаусы уже готовятся к выходу на работу. Здесь рождественские парки острова и праздники ближайших дней: ёлки, деревни, ярмарки.</p>
    <p class="counts"><span><b>${parks.length}</b> парка</span><span><b id="n-week">${week.length}</b> праздников в подборке</span></p>
  </header>

  <h2>Рождественские парки</h2>
  <ul class="parks" id="parks">${parks.map(parkCard).join('')}
  </ul>

  <h2>Праздники ближайших дней</h2>
  <div class="chips" role="group" aria-label="Что показать">
    <button type="button" class="chip" id="k-all" data-kind="" aria-pressed="true">Все <em id="n-all">${week.length}</em></button>
    ${kinds.map((k) => `<button type="button" class="chip" id="k-${k.t}" data-kind="${k.t}" aria-pressed="false">${k.label} <em>${k.n}</em></button>`).join('\n    ')}
  </div>
  <ul class="evs" id="evs">${week.map(eventRow).join('')}
  </ul>

  <footer>
    <span class="brand"><svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#9fd5f2"/><circle cx="23" cy="8.5" r="3.6" fill="#f26b21"/><path transform="translate(0 3)" d="M4.00 16.38 L5.34 17.01 L6.17 16.25 L7.10 15.49 L8.45 15.24 L9.90 15.75 L10.83 15.10 L10.83 13.27 L12.58 13.59 L14.85 13.80 L17.22 13.59 L19.80 13.16 L22.38 12.52 L24.96 11.23 L27.95 9.94 L26.51 11.02 L23.92 12.31 L21.55 13.91 L21.24 15.86 L22.69 17.79 L21.65 17.69 L19.28 17.79 L18.15 18.33 L17.84 19.40 L15.88 20.37 L13.09 20.69 L11.85 21.34 L11.02 22.20 L10.30 21.12 L8.45 21.12 L5.86 20.26 L5.03 19.08 L4.41 17.90 Z" fill="#0e1116"/></svg>Гид по Кипру</span>
    <span>Подборка от <a href="https://www.threads.net/@junky2s" target="_blank" rel="noopener">@junky2s</a> · обновлено ${updated}. Время, цены и программа могут меняться — перед поездкой проверяйте по ссылке на источник.</span>
  </footer>
</div>

<script>
  (function () {
    var MON = ${JSON.stringify(MON_FULL)};
    var DAYS = ['в воскресенье', 'в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу'];
    var today;
    try { today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Nicosia' }).format(new Date()); } catch (e) { today = new Date().toISOString().slice(0, 10); }
    var d = function (iso) { return new Date(iso + 'T12:00:00Z'); };
    var human = function (iso) { return d(iso).getUTCDate() + ' ' + MON[d(iso).getUTCMonth()]; };

    var parks = Array.prototype.slice.call(document.querySelectorAll('.park'));
    parks.forEach(function (li) {
      var s = li.dataset.start, e = li.dataset.end, t = li.dataset.time, el = li.querySelector('.status');
      if (e < today) { li.hidden = true; return; }
      if (s > today) {
        var n = Math.round((d(s) - d(today)) / 86400000);
        el.textContent = n === 1 ? 'Откроется завтра' + (t ? ' в ' + t : '') : n < 7 ? 'Откроется ' + DAYS[d(s).getUTCDay()] : 'Откроется ' + human(s);
        li.dataset.rank = 1;
      } else {
        el.textContent = e === today ? 'Сегодня последний день' : 'Работает до ' + human(e);
        el.classList.add('now'); li.dataset.rank = 0;
      }
    });
    var pl = document.getElementById('parks');
    parks.sort(function (a, b) { return (a.dataset.rank || 2) - (b.dataset.rank || 2); }).forEach(function (li) { pl.appendChild(li); });

    var evs = Array.prototype.slice.call(document.querySelectorAll('.ev'));
    evs.forEach(function (li) { if (li.dataset.end < today) li.remove(); });
    var live = Array.prototype.slice.call(document.querySelectorAll('.ev'));
    document.getElementById('n-all').textContent = live.length;
    document.getElementById('n-week').textContent = live.length;
    var chips = document.querySelectorAll('.chip');
    chips.forEach(function (c) {
      var k = c.dataset.kind;
      if (k) { var n = live.filter(function (li) { return li.dataset.kind === k; }).length; c.querySelector('em').textContent = n; c.hidden = !n; }
      c.addEventListener('click', function () {
        chips.forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
        live.forEach(function (li) { li.hidden = !!k && li.dataset.kind !== k; });
      });
    });
  })();
</script>
`;

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, html);
console.log(`standalone/christmas.html: ${parks.length} парков, ${week.length} праздников (${kinds.map((k) => `${k.label} ${k.n}`).join(', ')})`);
