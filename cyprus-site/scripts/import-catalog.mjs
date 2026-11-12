#!/usr/bin/env node
/**
 * Импорт внутренней базы компаний (Google Sheets → Файл → Скачать → CSV) в ЧЕРНОВИКИ сайта.
 *
 *   npm run import:catalog -- import/catalog.csv [--dry-run]
 *
 * Что делает:
 *  - берёт ТОЛЬКО публичные колонки (ID, категория, название, город, сайт, публичный канал, сеть);
 *  - отбрасывает email, телефоны, статусы переписки, заметки и любые внутренние поля;
 *  - создаёт src/content/companies/<slug>.yaml со status: draft;
 *  - не перезаписывает уже существующие файлы (их могли отредактировать вручную).
 *
 * Черновик на сайте не виден. Чтобы опубликовать: проверить данные по официальному источнику,
 * дописать summary/sources/verified_at и поставить status: published (см. README).
 *
 * Колонки исходной таблицы «Кипр — единый каталог…» (заголовки там технические: Column 1…23):
 *   1 ID · 2 категория · 3 подгруппа · 4 название · 5 город · 6 заметка · 7 сайт · 8 публичный канал
 *   9 языки · 10 сеть/бренд · 12–14 источник (внутр.) · 16 статус проверки · 20–22 контакты/CRM (внутр.)
 */
import fs from 'node:fs';
import path from 'node:path';
import { stringify } from 'yaml';

const COL = { id: 0, category: 1, name: 3, city: 4, website: 6, channel: 7, network: 9 };

// Соответствие исходных категорий разделам сайта (дублирует src/data/taxonomy.ts).
const MAP = {
  'Автомобили': ['cars', 'car-buying'],
  'Частные школы': ['education', 'private-schools'],
  'Греческий язык': ['education', 'greek'],
  'Недвижимость': ['property-home', 'real-estate'],
  'Ипотека и финансы': ['property-home', 'mortgage'],
  'Юридические услуги': ['property-home', 'legal'],
  'Дом и ремонт': ['property-home', 'home-repair'],
  'Аренда лодок': ['leisure-spa', 'boats'],
  'Бани и SPA': ['leisure-spa', 'spa'],
  'Отели и размещение': ['leisure-spa', 'hotels'],
  'Медицина и здоровье': ['health-beauty', 'medical'],
  'Красота и здоровье': ['health-beauty', 'tattoo'],
  'Кафе и рестораны': ['food', 'cafes'],
  'Билеты и афиша': ['entertainment', 'tickets'],
  'События и досуг': ['entertainment', 'organizers'],
  'Кино и развлечения': ['entertainment', 'cinema'],
  'Спорт и фитнес': ['other', 'sport'],
  'Спорт и досуг': ['other', 'sport'],
  'Магазины': ['other', 'shops'],
  'Цветы и подарки': ['other', 'flowers'],
};

function parseCSV(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') q = false;
      else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (ch !== '\r') cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

const TR = { а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'zh',з:'z',и:'i',й:'y',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'h',ц:'c',ч:'ch',ш:'sh',щ:'sch',ъ:'',ы:'y',ь:'',э:'e',ю:'yu',я:'ya' };
export const slugify = (s) => s.toLowerCase().replace(/[’']/g, '').split('').map((c) => TR[c] ?? c).join('')
  .normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/;
const clean = (v) => (v ?? '').trim();

/** Официальный сайт: только http(s)-ссылка без email. */
function website(v) {
  const s = clean(v);
  return /^https?:\/\/\S+$/.test(s) && !EMAIL.test(s) ? s : undefined;
}

/** Публичный канал: берём только ссылку на соцсеть/сайт; email и телефоны отбрасываем. */
function channel(v) {
  for (const part of clean(v).split(/[;,]\s*/)) {
    if (EMAIL.test(part)) continue;
    const url = part.match(/https?:\/\/\S+/)?.[0];
    if (url) return { label: url.includes('instagram.com') ? 'Instagram' : 'Ссылка', url };
    const handle = part.match(/^Instagram\s+@([\w.]+)$/i)?.[1];
    if (handle) return { label: `Instagram @${handle}`, url: `https://www.instagram.com/${handle}/` };
  }
  return undefined;
}

function main() {
  const args = process.argv.slice(2);
  const file = args.find((a) => !a.startsWith('--'));
  const dry = args.includes('--dry-run');
  if (!file) { console.error('Использование: npm run import:catalog -- <путь к CSV> [--dry-run]'); process.exit(1); }

  const rows = parseCSV(fs.readFileSync(file, 'utf8')).filter((r) => r.some((c) => c.trim()));
  const outDir = path.resolve('src/content/companies');
  fs.mkdirSync(outDir, { recursive: true });

  const stats = { created: 0, skippedExisting: 0, skippedHeader: 0, unknownCategory: [] };
  // Повторный импорт безопасен: записи узнаются по source_id, уже созданные файлы не трогаем.
  const existingFiles = fs.readdirSync(outDir).filter((f) => /\.ya?ml$/.test(f));
  const used = new Set(existingFiles.map((f) => f.replace(/\.ya?ml$/, '')));
  const knownIds = new Set(existingFiles.map((f) => fs.readFileSync(path.join(outDir, f), 'utf8').match(/^source_id:\s*(\S+)/m)?.[1]).filter(Boolean));

  for (const r of rows) {
    const id = clean(r[COL.id]);
    if (!/^[A-Z]+-\d+$/.test(id)) { stats.skippedHeader++; continue; } // заголовок или пустая строка
    if (knownIds.has(id)) { stats.skippedExisting++; continue; }
    const mapped = MAP[clean(r[COL.category])];
    if (!mapped) { stats.unknownCategory.push(`${id}: ${r[COL.category]}`); continue; }

    const name = clean(r[COL.name]);
    const city = clean(r[COL.city]);
    // Уникальный адрес: название → название-город (филиал сети) → название-ID.
    const base = slugify(name) || id.toLowerCase();
    const slug = [base, city && `${base}-${slugify(city)}`, `${base}-${id.toLowerCase()}`].find((s) => s && !used.has(s));
    used.add(slug);

    const network = clean(r[COL.network]);
    const doc = {
      name,
      status: 'draft',
      section: mapped[0],
      category: mapped[1],
      ...(city && !['Кипр'].includes(city) && { city }),
      ...(network && network !== name && { network }),
      ...(website(r[COL.website]) && { website: website(r[COL.website]) }),
      ...(channel(r[COL.channel]) && { channel: channel(r[COL.channel]) }),
      sources: [],
      source_id: id,
    };
    const header = '# Черновик из внутренней базы. Данные НЕ проверены: сверить по официальному источнику,\n'
      + '# заполнить summary, description, sources, verified_at и только затем поставить status: published.\n';
    if (!dry) fs.writeFileSync(path.join(outDir, `${slug}.yaml`), header + stringify(doc));
    stats.created++;
  }
  console.log(`${dry ? '[dry-run] ' : ''}Создано черновиков: ${stats.created}; уже существовали: ${stats.skippedExisting}; пропущено служебных строк: ${stats.skippedHeader}`);
  if (stats.unknownCategory.length) console.log('Неизвестные категории (добавьте в MAP и taxonomy.ts):\n  ' + stats.unknownCategory.join('\n  '));
}

main();
