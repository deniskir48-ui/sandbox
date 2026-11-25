// Картинка-превью для Threads, Telegram и соцсетей (1200×630) в облике «Медь и афишная тумба» (DEC-W51).
//   node scripts/og-image.cjs standalone/og-afisha.png afisha
//   node scripts/og-image.cjs standalone/og-christmas.png christmas
//   node scripts/og-image.cjs static/cyprus/green-points/og.png green-points
// Рендер через Playwright; шрифты — Google Fonts (как на сайте).
const { chromium } = require('playwright');
const I = {
  park: '<circle cx="12" cy="9.5" r="6.5"/><circle cx="12" cy="9.5" r="1.2"/><path d="M12 3v5.3M12 10.7V16M5.5 9.5h5.3M13.2 9.5h5.3M10.8 15.9 8.5 21M13.2 15.9l2.3 5.1M6.5 21h11"/>',
  village: '<path d="M3.5 11 12 4l8.5 7M5.5 9.5V20h13V9.5M10 20v-5h4v5M15.5 6.9V4.5H18V9"/>',
  tree: '<path d="M12 3 7.5 9H10l-4 5.5h3.5L5 20h14l-4.5-5.5H18L14 9h2.5zM12 20v2"/>',
  market: '<path d="M4.5 4h15l2 5h-19zM9.5 4 9 9M14.5 4l.5 5M5 9v11M19 9v11M3 20h18M5 14h14"/>',
  workshop: '<circle cx="6.5" cy="17.5" r="3"/><circle cx="17.5" cy="17.5" r="3"/><path d="M8.6 15.4 17 3.5M15.4 15.4 7 3.5"/>',
  concert: '<circle cx="7.5" cy="17.5" r="3"/><path d="M10.5 17.5V4l7.5 3.5"/>',
  ticket: '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h13A1.5 1.5 0 0 1 20 7.5V10a2 2 0 0 0 0 4v2.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16.5V14a2 2 0 0 0 0-4z"/><path d="M14.5 6.5v2M14.5 11v2M14.5 15.5v2"/>',
  kids: '<path d="M12 16c-3.5 0-6-3.4-6-7a6 6 0 0 1 12 0c0 3.6-2.5 7-6 7zM11 17.5h2L12 16zM12 17.5c-1.5 1.5 1.5 2.5 0 4.5"/>',
  star: '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z"/>',
  pin: '<path d="M12 21s-6.5-5.6-6.5-10.5a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.3"/>',
  mountain: '<path d="M3 19.5 9.5 8.5l4 6.5 2.5-3.8 5 8.3z"/><circle cx="17" cy="5.8" r="1.8"/>',
};
const MARK = '<rect width="32" height="32" rx="9" fill="#A24F22"/><path d="M16 3.6c-5.5 0-9.6 4.1-9.6 9.4 0 6.7 9.6 15.2 9.6 15.2s9.6-8.5 9.6-15.2c0-5.3-4.1-9.4-9.6-9.4z" fill="#F3F5F4"/><circle cx="16" cy="13" r="5.8" fill="#A24F22"/><path d="M19.4 9.6l-2.3 4.5-2.2-2.2z" fill="#13263B"/><path d="M12.6 16.4l2.3-4.5 2.2 2.2z" fill="#F3F5F4"/>';
const GP = process.argv[3] === 'green-points';
const AF = !GP && process.argv[3] !== 'christmas';
const chips = GP ? [['pin', 'Лимассол', '#1B6E62'], ['pin', 'Никосия', '#1B6E62'], ['pin', 'Ларнака', '#1B6E62'], ['pin', 'Пафос', '#1B6E62']] : AF
  ? [['kids', 'Детям', '#AD2E68'], ['concert', 'Музыка', '#1F5FA3'], ['ticket', 'Театр и кино', '#A8432A'], ['star', 'Фестивали', '#8A5B00'], ['workshop', 'Мастер-классы', '#6345A8']]
  : [['park', 'Парки', '#A24F22'], ['village', 'Деревни', '#1F5FA3'], ['tree', 'Зажжение огней', '#28744A'], ['market', 'Ярмарки', '#8A5B00']];
const bulbs = [[40, 19, '#e0a537'], [95, 28, '#5aa6d6'], [150, 26, '#d0662b'], [205, 15, '#e0a537'], [260, 21, '#3f9a6b'], [315, 28, '#5aa6d6'], [365, 21, '#d0662b'], [415, 14, '#e0a537'], [470, 22, '#5aa6d6'], [520, 28, '#3f9a6b'], [570, 21, '#d0662b'], [620, 14, '#e0a537'], [675, 22, '#5aa6d6'], [725, 27, '#d0662b'], [775, 15, '#e0a537']];
const html = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@500;600;700&family=Fira+Sans+Extra+Condensed:wght@700&display=block">
<style>
  html, body { margin: 0; }
  body { width: 1200px; height: 630px; overflow: hidden; background: #F3F5F4; color: #13263B; font-family: Onest, sans-serif; position: relative; border-top: 10px solid #A24F22; box-sizing: border-box; }
  svg.g { position: absolute; top: 96px; left: 0; width: 1200px; height: 70px; }
  .brand { position: absolute; left: 80px; top: 44px; display: flex; align-items: center; gap: 14px; font: 700 30px Onest; }
  .box { position: absolute; left: 80px; right: 80px; bottom: 92px; }
  h1 { font: 700 168px/0.92 "Fira Sans Extra Condensed", sans-serif; margin: 0; letter-spacing: -.01em; }
  p { font: 500 30px/1.3 Onest; color: #566675; margin: 22px 0 0; }
  .row { display: flex; gap: 12px; margin-top: 34px; }
  .c { display: inline-flex; align-items: center; gap: 9px; padding: 10px 18px; border-radius: 999px; font: 600 23px Onest; border: 2px solid; background: #fff; }
  .c svg { width: 26px; height: 26px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
</style></head><body>
<div class="brand"><svg width="44" height="44" viewBox="0 0 32 32">${MARK}</svg>City Compas</div>
${AF || GP ? '' : `<svg class="g" viewBox="0 0 800 50" preserveAspectRatio="none"><path d="M0 8 Q100 42 200 14 T400 14 T600 14 T800 8" fill="none" stroke="#9aa9b5" stroke-width="2"/>${bulbs.map(([x, y, c]) => `<ellipse cx="${x}" cy="${y}" rx="4" ry="6" fill="${c}"/>`).join('')}</svg>`}
<div class="box">
  <h1${AF ? '' : ' style="font-size:118px;white-space:nowrap"'}>${GP ? 'Green Points Кипра' : AF ? 'Афиша Кипра' : 'Рождество на Кипре'}</h1>
  <p>${GP ? 'Где бесплатно сдать мебель, технику, ветки и батарейки' : AF ? 'Концерты, спектакли, выставки и детские события на неделю' : 'Парки, рождественские деревни, ярмарки и зажжение огней'}</p>
  <div class="row">${chips.map(([k, t, c]) => `<span class="c" style="color:${c};border-color:${c}"><svg viewBox="0 0 24 24">${I[k]}</svg>${t}</span>`).join('')}</div>
</div>
</body></html>`;
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await p.setContent(html, { waitUntil: 'networkidle' }); await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: process.argv[2] }); await b.close();
})();
