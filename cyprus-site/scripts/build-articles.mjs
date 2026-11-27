/**
 * Раздел «Статьи» (DEC-W55): /cyprus/articles/ — список, /cyprus/articles/<slug>/ — статья.
 * Источник — src/content/articles/*.md (те же файлы, что у основного сайта на Astro); публикуются только status: published.
 * Markdown → HTML: micromark + GFM (таблицы). Заголовкам можно задать якорь: «## Осмотр {#inspection}».
 * Облик — как у афиши («Медь и афишная тумба», DEC-W51). Вызывается из scripts/build-site.mjs.
 */
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';
import { micromark } from 'micromark';
import { gfm, gfmHtml } from 'micromark-extension-gfm';

const DIR = path.resolve('src/content/articles');
const MON_FULL = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const dateRu = (d) => { const x = new Date(d); return `${x.getUTCDate()} ${MON_FULL[x.getUTCMonth()]} ${x.getUTCFullYear()}`; };
const iso = (d) => new Date(d).toISOString().slice(0, 10);
// Минуты чтения: ~180 слов в минуту.
const minutes = (md) => Math.max(1, Math.round(md.replace(/[#*|[\]()>-]/g, ' ').split(/\s+/).filter(Boolean).length / 180));
const plural = (n, a, b, c) => (n % 10 === 1 && n % 100 !== 11 ? a : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? b : c);

export function loadArticles() {
  return fs.readdirSync(DIR).filter((f) => f.endsWith('.md')).map((f) => {
    const raw = fs.readFileSync(path.join(DIR, f), 'utf8');
    const m = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    const meta = yaml.load(m[1]);
    return { slug: f.slice(0, -3), ...meta, body: m[2] };
  }).filter((a) => a.status === 'published').sort((a, b) => iso(b.published_at).localeCompare(iso(a.published_at)));
}

function render(md) {
  let html = micromark(md, { extensions: [gfm()], htmlExtensions: [gfmHtml()] });
  // Якоря заголовков: «Текст {#id}» → id="id".
  html = html.replace(/<h([23])>([\s\S]*?)\s*\{#([\w-]+)\}<\/h\1>/g, '<h$1 id="$3">$2</h$1>');
  // Номер шага в заголовке («1. Ищете машину») — крупной цифрой: это настоящая последовательность.
  html = html.replace(/<h2 id="([\w-]+)">(\d+)\.\s+/g, '<h2 id="$1"><span class="n">$2</span>');
  // Внешние ссылки — в новой вкладке; внутренние якоря — как есть.
  html = html.replace(/<a href="(https?:\/\/[^"]+)">/g, '<a href="$1" target="_blank" rel="noopener">');
  // Таблицы прокручиваются внутри себя, если не помещаются.
  html = html.replace(/<table>/g, '<div class="tbl"><table>').replace(/<\/table>/g, '</table></div>');
  return html;
}

const CSS = `
    /* Статьи в облике сайта: известняк, чернила, медь и патина; узкий плакатный шрифт в заголовках, Onest в тексте.
       Колонка текста ~68 знаков; шаги — крупными медными цифрами. */
    :root {
      color-scheme: light;
      --night: #F3F5F4; --card: #FFFFFF; --line: #D4DDD9; --text: #13263B; --muted: #566675; --copper: #A24F22; --patina: #1B6E62;
      --gutter: max(16px, env(safe-area-inset-left, 0px));
      --display: "Fira Sans Extra Condensed", "Onest", system-ui, sans-serif; --body: "Onest", system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    html { background: var(--night); }
    body { margin: 0; background: var(--night); color: var(--text); font-family: var(--body); font-size: 17px; line-height: 1.6;
      padding-left: var(--gutter); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 40px; }
    .wrap { max-width: 1240px; margin: 0 auto; }
    .ic { flex: none; width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
    .topbar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 12; display: flex; align-items: center; justify-content: space-between; gap: 10px;
      padding-block: 10px; background: var(--night); border-bottom: 1px solid transparent; }
    .topbar.stuck { border-bottom-color: var(--line); }
    .tb-brand { display: inline-flex; align-items: center; gap: 8px; min-width: 0; color: var(--text); text-decoration: none; font-weight: 700; font-size: .86rem; white-space: nowrap; }
    .tb-brand svg { flex: none; }
    @media (min-width: 640px) { .tb-brand { font-size: .95rem; } }
    @media (max-width: 479px) { .tb-brand span { display: none; } }
    .tabs { display: flex; gap: 3px; padding: 3px; background: var(--card); border: 1px solid var(--line); border-radius: 999px; }
    .tabs a { display: inline-flex; align-items: center; gap: 5px; min-height: 34px; box-sizing: border-box; padding: 7px 10px; border-radius: 999px; color: var(--muted); font: 600 .86rem var(--body); text-decoration: none; white-space: nowrap; }
    @media (min-width: 640px) { .tabs a { padding: 7px 13px; font-size: .9rem; } }
    .tabs a .ic { color: var(--patina); }
    @media (max-width: 419px) { .tabs a .ic { display: none; } }
    .tabs a:hover { color: var(--text); }
    .tabs a[aria-current] { background: var(--text); color: #fff; } .tabs a[aria-current] .ic { color: inherit; }
    a:focus-visible { outline: 2px solid var(--copper); outline-offset: 2px; }

    .art, .idx { max-width: 720px; margin: 0 auto; padding-top: 14px; }
    .crumb { font-size: .9rem; } .crumb a { color: var(--patina); text-underline-offset: 3px; }
    h1 { font-family: var(--display); font-weight: 700; font-size: clamp(2.1rem, 7.6vw, 3.3rem); line-height: 1; letter-spacing: -.005em; margin: 8px 0 0; text-wrap: balance; }
    .meta { margin: 14px 0 0; color: var(--muted); font-size: .9rem; }
    .body { margin-top: 22px; }
    .body > p:first-child, .body > p:first-child + p { font-size: 1.08rem; }
    .body p, .body ul, .body ol { margin: 0 0 14px; }
    .body h2 { font-family: var(--display); font-weight: 700; font-size: 1.85rem; line-height: 1.05; margin: 40px 0 14px; text-wrap: balance; scroll-margin-top: 70px;
      display: flex; align-items: baseline; gap: 12px; }
    .body h2 .n { flex: none; font-size: 2.6rem; color: var(--copper); line-height: .9; font-variant-numeric: tabular-nums; }
    .body h3 { font-family: var(--display); font-weight: 600; font-size: 1.35rem; margin: 26px 0 8px; scroll-margin-top: 70px; }
    .body ul, .body ol { padding-left: 1.25em; display: grid; gap: 6px; }
    .body li::marker { color: var(--copper); }
    .body strong { font-weight: 650; }
    .body a { color: var(--patina); text-underline-offset: 3px; text-decoration-thickness: 1px; }
    .body a:hover { text-decoration-thickness: 2px; }
    /* «Коротко: весь путь» — оглавление шагов. */
    .body #steps + ol { list-style: none; counter-reset: s; padding: 14px 18px; background: var(--card); border: 1px solid var(--line); border-radius: 6px; gap: 2px; }
    .body #steps + ol li { counter-increment: s; display: grid; grid-template-columns: 30px minmax(0, 1fr); align-items: baseline; }
    .body #steps + ol li::before { content: counter(s); font: 700 1.4rem/1 var(--display); color: var(--copper); }
    .body #steps + ol a { color: var(--text); text-decoration: none; }
    .body #steps + ol a:hover { text-decoration: underline; }
    .tbl { overflow-x: auto; margin: 0 0 14px; }
    table { border-collapse: collapse; min-width: 280px; font-variant-numeric: tabular-nums; }
    th, td { text-align: left; padding: 8px 18px 8px 0; border-bottom: 1px solid var(--line); }
    th { font-size: .82rem; color: var(--muted); font-weight: 600; }

    .list { list-style: none; padding: 0; margin: 22px 0 0; border-top: 1px solid var(--line); }
    .list li { border-bottom: 1px solid var(--line); }
    .list a { display: grid; gap: 4px; padding: 18px 0; color: inherit; text-decoration: none; }
    .list a:hover b { text-decoration: underline; text-underline-offset: 4px; }
    .list b { font: 700 1.6rem/1.05 var(--display); text-wrap: balance; }
    .list span { color: var(--muted); }
    .list small { color: var(--muted); font-size: .85rem; }

    footer { max-width: 720px; margin: 44px auto 0; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: .9rem; display: grid; gap: 8px; }
    footer .brand { display: inline-flex; align-items: center; gap: 8px; color: var(--text); font-weight: 700; }
    .fnav { display: flex; flex-wrap: wrap; gap: 6px 18px; } .fnav a { color: var(--patina); text-underline-offset: 3px; } .fnav span { color: var(--text); }
`;

export function buildArticles({ SITE_DIR, SITE_URL, SITE_NAME, MARK, svg, esc, nav, artifactOut }) {
  const list = loadArticles();
  const fonts = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Fira+Sans+Extra+Condensed:wght@600;700&display=swap">';
  // Верхняя полоса и подвал — те же разделы, что на афише; в артефакте ссылки ведут на сайт.
  const shell = (current, artifact) => ({
    top: `<nav class="topbar" aria-label="Разделы">
    <a class="tb-brand" aria-label="City Compas" href="${artifact ? SITE_URL : ''}/cyprus/afisha/"><svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">${MARK}</svg><span>${esc(SITE_NAME)}</span></a>
    <div class="tabs">${nav.map((n) => `<a href="${artifact ? SITE_URL : ''}${n.path}"${n.path === current ? ' aria-current="page"' : ''}>${svg(n.icon)}${esc(n.tab)}</a>`).join('')}</div>
  </nav>`,
    foot: `<footer>
    <span class="brand"><svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">${MARK}</svg>${esc(SITE_NAME)}</span>
    <span>${esc(SITE_NAME)} — гид по Кипру на русском: что происходит, куда сходить и к кому обратиться.</span>
    <nav class="fnav" aria-label="Разделы сайта">${nav.map((n) => (n.path === current ? `<span>${esc(n.nav)}</span>` : `<a href="${artifact ? SITE_URL : ''}${n.path}">${esc(n.nav)}</a>`)).join('')}<a href="${artifact ? SITE_URL : ''}/cyprus/green-points/">Green Points</a></nav>
  </footer>
  <script>(function () { var b = document.querySelector('.topbar'); addEventListener('scroll', function () { b.classList.toggle('stuck', scrollY > 4); }, { passive: true }); })();</script>`,
  });
  const head = ({ title, description, url, image, type, ld }) => `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#F3F5F4">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="${type}"><meta property="og:locale" content="ru_RU"><meta property="og:site_name" content="${esc(SITE_NAME)}">
<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(description)}"><meta property="og:url" content="${url}">
<meta property="og:image" content="${image}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">
${fonts}
<style>${CSS}</style>${ld ? `\n<script type="application/ld+json">${JSON.stringify(ld).replace(/</g, '\\u003c')}</script>` : ''}
</head>
<body>`;
  const IDX = '/cyprus/articles/';

  const articlePage = (a, artifact) => {
    const url = `${SITE_URL}${IDX}${a.slug}/`, s = shell(IDX, artifact), min = minutes(a.body);
    const ld = { '@context': 'https://schema.org', '@type': 'Article', headline: a.title, description: a.description, datePublished: iso(a.published_at),
      dateModified: iso(a.updated_at ?? a.published_at), inLanguage: 'ru', mainEntityOfPage: url, image: `${url}og.png`, publisher: { '@type': 'Organization', name: SITE_NAME, url: SITE_URL } };
    const inner = `<div class="wrap">
  ${s.top}
  <main class="art">
    <p class="crumb"><a href="${artifact ? SITE_URL : ''}${IDX}">Статьи</a></p>
    <h1>${esc(a.title)}</h1>
    <p class="meta">${dateRu(a.updated_at ?? a.published_at)}, читать ${min} ${plural(min, 'минуту', 'минуты', 'минут')}</p>
    <div class="body">
${render(a.body)}
    </div>
  </main>
  ${s.foot}
</div>`;
    return artifact
      ? `<title>${esc(a.title.split(':')[0])}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n${fonts}\n<style>${CSS}</style>\n${inner}`
      : `${head({ title: a.title, description: a.description, url, image: `${url}og.png`, type: 'article', ld })}\n${inner}\n</body>\n</html>\n`;
  };

  // Список: опубликованные статьи и полезные страницы сайта (Green Points).
  const items = [
    ...list.map((a) => ({ href: `${IDX}${a.slug}/`, title: a.title, text: a.description, small: `${dateRu(a.published_at)}, читать ${minutes(a.body)} ${plural(minutes(a.body), 'минуту', 'минуты', 'минут')}` })),
    { href: '/cyprus/green-points/', title: 'Green Points Кипра: карта, часы работы, что принимают', text: 'Где бесплатно сдать старую мебель, технику, ветки, батарейки и краску: все площадки на карте, часы и телефоны.', small: 'Карта' },
  ];
  const idxUrl = `${SITE_URL}${IDX}`, si = shell(IDX, false);
  const index = `${head({ title: 'Полезные статьи о жизни на Кипре', description: 'Инструкции для жизни на Кипре: как купить машину, где сдать мусор и другое.', url: idxUrl, image: `${idxUrl}og.png`, type: 'website' })}
<div class="wrap">
  ${si.top}
  <main class="idx">
    <h1>Полезные статьи</h1>
    <ul class="list">${items.map((i) => `
      <li><a href="${i.href}"><b>${esc(i.title)}</b><span>${esc(i.text)}</span><small>${esc(i.small)}</small></a></li>`).join('')}
    </ul>
  </main>
  ${si.foot}
</div>
</body>
</html>
`;
  fs.mkdirSync(path.join(SITE_DIR, IDX), { recursive: true });
  fs.writeFileSync(path.join(SITE_DIR, IDX, 'index.html'), index);
  for (const a of list) {
    const dir = path.join(SITE_DIR, IDX, a.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'index.html'), articlePage(a, false));
    const og = path.resolve('static/cyprus/articles', a.slug, 'og.png');
    if (!fs.existsSync(og)) console.log(`нет картинки-превью: node scripts/og-image.cjs ${path.relative(process.cwd(), og)} text "${a.title.split(':')[0]}" "${a.description.slice(0, 70)}"`);
  }
  if (artifactOut && list[0]) fs.writeFileSync(artifactOut, articlePage(list[0], true));
  console.log(`site${IDX}: ${list.length} ${plural(list.length, 'статья', 'статьи', 'статей')} + Green Points`);
}
