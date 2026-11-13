#!/usr/bin/env node
/**
 * Проверка данных перед сборкой (запускается автоматически в `npm run build`).
 * Ошибки — сборка останавливается. Предупреждения — только выводятся.
 *  - в публичных полях опубликованных записей нет email и телефонов;
 *  - статьи ссылаются только на опубликованные компании;
 *  - организатор события — опубликованная компания;
 *  - даты проверки не в будущем; устаревшие проверки (компании > 180 дней) — предупреждение;
 *  - в src/content нет технических фикстур;
 *  - каждое место (city) привязано к району фильтра (src/data/regions.json) — предупреждение.
 */
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'yaml';

const ROOT = path.resolve('src/content');
const errors = [], warnings = [];
const today = new Date().toISOString().slice(0, 10);

const readYaml = (dir) => fs.existsSync(dir)
  ? fs.readdirSync(dir).filter((f) => /\.ya?ml$/.test(f)).map((f) => ({ id: f.replace(/\.ya?ml$/, ''), file: path.join(dir, f), data: parse(fs.readFileSync(path.join(dir, f), 'utf8')) ?? {} }))
  : [];
const readMd = (dir) => fs.existsSync(dir)
  ? fs.readdirSync(dir).filter((f) => f.endsWith('.md')).map((f) => {
      const raw = fs.readFileSync(path.join(dir, f), 'utf8');
      const fm = raw.match(/^---\n([\s\S]*?)\n---/)?.[1] ?? '';
      return { id: f.replace(/\.md$/, ''), file: path.join(dir, f), data: parse(fm) ?? {}, body: raw };
    })
  : [];

const companies = readYaml(path.join(ROOT, 'companies'));
const events = readYaml(path.join(ROOT, 'events'));
const articles = readMd(path.join(ROOT, 'articles'));
const published = new Set(companies.filter((c) => c.data.status === 'published').map((c) => c.id));

const EMAIL = /[\w.+-]+@[\w-]+\.[a-z]{2,}/i;
const PHONE = /\+?\d[\d\s-]{8,}\d/;
const PUBLIC_FIELDS = ['name', 'title', 'city', 'venue', 'summary', 'description', 'network', 'price'];
const isoOf = (v) => (v instanceof Date ? v.toISOString().slice(0, 10) : String(v ?? ''));
const daysAgo = (iso) => Math.round((Date.parse(today) - Date.parse(iso)) / 86400000);

for (const item of [...companies, ...events]) {
  const d = item.data;
  const rel = path.relative('.', item.file);
  if (/фикстур|fixture/i.test(`${d.name ?? ''}${d.title ?? ''}`)) errors.push(`${rel}: похоже на тестовую фикстуру в боевых данных`);
  if (d.status !== 'published') continue;
  for (const f of PUBLIC_FIELDS) {
    const v = String(d[f] ?? '');
    if (EMAIL.test(v)) errors.push(`${rel}: email в публичном поле «${f}»`);
    if (f !== 'price' && PHONE.test(v)) warnings.push(`${rel}: похоже на телефон в поле «${f}» — убедитесь, что это официальный публичный номер`);
  }
  const v = isoOf(d.verified_at);
  if (v && v > today) errors.push(`${rel}: дата проверки ${v} в будущем`);
  if (v && companies.includes(item) && daysAgo(v) > 180) warnings.push(`${rel}: проверка старше 180 дней (${v}) — перепроверить`);
  if (events.includes(item) && d.organizer && !published.has(d.organizer)) errors.push(`${rel}: организатор «${d.organizer}» не опубликован в Гиде`);
}

for (const a of articles) {
  if (a.data.status !== 'published') continue;
  const rel = path.relative('.', a.file);
  for (const slug of a.data.companies ?? []) {
    if (!published.has(slug)) errors.push(`${rel}: компания «${slug}» в списке companies не опубликована`);
  }
  for (const m of a.body.matchAll(/\]\(\/services\/([\w-]+)\/?\)/g)) {
    if (!published.has(m[1])) errors.push(`${rel}: ссылка на неопубликованную компанию /services/${m[1]}/`);
  }
}

// Места без района попадают в фильтре в «Другие места» — подсказать, что их стоит добавить в справочник.
const REGIONS = JSON.parse(fs.readFileSync(path.resolve('src/data/regions.json'), 'utf8'));
const unmapped = new Map();
for (const item of [...companies, ...events]) {
  const city = item.data.city;
  if (city && !REGIONS.places[city]) unmapped.set(city, [...(unmapped.get(city) ?? []), item.id]);
}
for (const [city, ids] of unmapped) warnings.push(`место «${city}» не привязано к району в src/data/regions.json — в фильтре будет в «${REGIONS.other}» (${ids.slice(0, 3).join(', ')}${ids.length > 3 ? '…' : ''})`);

const drafts = companies.length - published.size;
console.log(`Компании: опубликовано ${published.size}, черновиков ${drafts}. События: ${events.filter((e) => e.data.status === 'published').length} опубл. Статьи: ${articles.filter((a) => a.data.status === 'published').length} опубл.`);
warnings.forEach((w) => console.warn('⚠ ' + w));
if (errors.length) { errors.forEach((e) => console.error('✖ ' + e)); process.exit(1); }
console.log('Проверка данных пройдена.');
