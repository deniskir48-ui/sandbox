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

const COL = { id: 0, category: 1, type: 2, name: 3, city: 4, note: 5, website: 6, channel: 7, languages: 8, network: 9 };

// Соответствие исходных категорий разделам сайта (дублирует src/data/taxonomy.ts).
const MAP = {
  'Автомобили': ['cars', 'japan-import'], // уточняется по типу услуги, см. carCategory()
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

/** Тип услуги из колонки 3 без служебных пометок «(группа CRM)», «(уточнить)» и т. п. */
function serviceType(v) {
  const s = clean(v).replace(/\s*\((группа CRM|категория CRM|CRM|из черновика|уточнить|тип уточнить)\)\s*/gi, '').trim();
  // Не обещаем подготовку к экзамену, пока она не подтверждена официальным источником.
  if (/подготовка A2/i.test(s)) return 'Курсы греческого языка';
  return s || undefined;
}

/** Короткая фактическая пометка о формате из колонки 6 (например, «Баня на дровах»). Служебные заметки отбрасываются. */
function formatNote(v) {
  const s = clean(v);
  if (!s || /^Языки по базе|отзыв/i.test(s)) return undefined; // служебное или личный отзыв
  if (/не подтвержд|уточнить/i.test(s)) return clean(s.split(';')[0]) || undefined; // оставляем только факт до «;»
  return s.replace(/;\s*/g, '. ');
}

/** Подкатегория авто по типу услуги из базы; окончательно проверяется по сайту компании. */
function carCategory(type) {
  const t = clean(type).toLowerCase();
  if (/аренд|прокат|rent/.test(t)) return 'car-rental';
  if (/подбор/.test(t)) return 'car-selection';
  if (/нов(ые|ых)|дилер/.test(t)) return 'new-cars';
  return 'japan-import';
}

function main() {
  const args = process.argv.slice(2);
  const file = args.find((a) => !a.startsWith('--'));
  const dry = args.includes('--dry-run');
  const refresh = args.includes('--refresh-drafts'); // обновить поля в непроверенных черновиках (без verified_at)
  if (!file) { console.error('Использование: npm run import:catalog -- <путь к CSV> [--dry-run]'); process.exit(1); }

  const rows = parseCSV(fs.readFileSync(file, 'utf8')).filter((r) => r.some((c) => c.trim()));
  const outDir = path.resolve('src/content/companies');
  fs.mkdirSync(outDir, { recursive: true });

  const stats = { created: 0, refreshed: 0, skippedExisting: 0, skippedHeader: 0, unknownCategory: [] };
  // Повторный импорт безопасен: записи узнаются по source_id, уже созданные файлы не трогаем.
  const existingFiles = fs.readdirSync(outDir).filter((f) => /\.ya?ml$/.test(f));
  const used = new Set(existingFiles.map((f) => f.replace(/\.ya?ml$/, '')));
  const known = new Map(); // source_id → { file, draft }
  for (const f of existingFiles) {
    const txt = fs.readFileSync(path.join(outDir, f), 'utf8');
    const sid = txt.match(/^source_id:\s*(\S+)/m)?.[1];
    // Проверенные черновики (есть verified_at, ждут утверждения) импорт не перезаписывает.
    if (sid) known.set(sid, { file: f, draft: /^status:\s*draft/m.test(txt) && !/^verified_at:/m.test(txt) });
  }

  for (const r of rows) {
    const id = clean(r[COL.id]);
    if (!/^[A-Z]+-\d+$/.test(id)) { stats.skippedHeader++; continue; } // заголовок или пустая строка
    const prev = known.get(id);
    if (prev && !(refresh && prev.draft)) { stats.skippedExisting++; continue; }
    const mapped = MAP[clean(r[COL.category])];
    if (!mapped) { stats.unknownCategory.push(`${id}: ${r[COL.category]}`); continue; }

    const name = clean(r[COL.name]);
    const city = clean(r[COL.city]);
    // Уникальный адрес: название → название-город (филиал сети) → название-ID.
    const base = slugify(name) || id.toLowerCase();
    const slug = prev ? prev.file.replace(/\.ya?ml$/, '')
      : [base, city && `${base}-${slugify(city)}`, `${base}-${id.toLowerCase()}`].find((s) => s && !used.has(s));
    used.add(slug);

    const network = clean(r[COL.network]);
    const doc = {
      name,
      status: 'draft',
      section: mapped[0],
      category: mapped[0] === 'cars' ? carCategory(r[COL.type]) : mapped[1],
      ...(city && !['Кипр'].includes(city) && { city }),
      ...(network && network !== name && { network }),
      ...(serviceType(r[COL.type]) && { service_type: serviceType(r[COL.type]) }),
      ...(clean(r[COL.languages]) && { languages: clean(r[COL.languages]) }),
      ...(formatNote(r[COL.note]) && { summary: formatNote(r[COL.note]) }),
      ...(website(r[COL.website]) && { website: website(r[COL.website]) }),
      ...(channel(r[COL.channel]) && { channel: channel(r[COL.channel]) }),
      sources: [],
      source_id: id,
    };
    const header = '# Черновик из внутренней базы. Данные НЕ проверены: сверить по официальному источнику,\n'
      + '# заполнить summary, description, sources, verified_at и только затем поставить status: published.\n';
    if (!dry) fs.writeFileSync(path.join(outDir, `${slug}.yaml`), header + stringify(doc));
    prev ? stats.refreshed++ : stats.created++;
  }
  console.log(`${dry ? '[dry-run] ' : ''}Создано черновиков: ${stats.created}; обновлено черновиков: ${stats.refreshed}; уже существовали: ${stats.skippedExisting}; пропущено служебных строк: ${stats.skippedHeader}`);
  if (stats.unknownCategory.length) console.log('Неизвестные категории (добавьте в MAP и taxonomy.ts):\n  ' + stats.unknownCategory.join('\n  '));
}

main();
