import { getCollection, type CollectionEntry } from 'astro:content';
import { todayInCyprus } from './dates';
import { PREVIEW_DRAFTS } from '../config';

export type Company = CollectionEntry<'companies'>;
export type Event = CollectionEntry<'events'>;
export type Article = CollectionEntry<'articles'>;

// Порядок: сначала Verified (DEC-W29), затем опубликованные → проверенные черновики → непроверенные
// (черновики видны только в предпросмотре), внутри — по алфавиту.
const rank = (c: Company) => (c.data.status === 'published' ? 0 : c.data.verified_at ? 1 : 2);
/** Все подкатегории компании: основная + дополнительные. */
export const categoriesOf = (c: Company): string[] => [c.data.category, ...c.data.extra_categories];
const byName = (a: Company, b: Company) =>
  Number(b.data.verified_badge) - Number(a.data.verified_badge) || rank(a) - rank(b) || a.data.name.localeCompare(b.data.name, 'ru');

/** Только опубликованные (проверенные) компании. Черновики видны лишь в режиме предпросмотра PREVIEW_DRAFTS=1. */
export async function getPublishedCompanies(): Promise<Company[]> {
  return (await getCollection('companies', (e) => PREVIEW_DRAFTS || e.data.status === 'published')).sort(byName);
}

export async function getPublishedArticles(): Promise<Article[]> {
  const list = await getCollection('articles', (e) => PREVIEW_DRAFTS || e.data.status === 'published');
  const ts = (a: Article) => (a.data.updated_at ?? a.data.published_at).getTime();
  return list.sort((a, b) => ts(b) - ts(a));
}

/** Последний день события (для многодневных — end_date). */
export const eventLastDay = (e: Event) => e.data.end_date ?? e.data.date;

export const isUpcoming = (e: Event, today = todayInCyprus()) => eventLastDay(e) >= today;

const eventKey = (e: Event) => `${e.data.date}T${e.data.time ?? '00:00'}`;

/** Все опубликованные события (включая прошедшие — для страниц с пометкой «прошло»). В предпросмотре — и черновики. */
export async function getPublishedEvents(): Promise<Event[]> {
  return (await getCollection('events', (e) => PREVIEW_DRAFTS || e.data.status === 'published')).sort((a, b) =>
    eventKey(a).localeCompare(eventKey(b)),
  );
}

/** Предстоящие события: сначала по приоритету редактора, внутри — по дате и времени. */
export async function getUpcomingEvents(): Promise<Event[]> {
  const today = todayInCyprus();
  return (await getPublishedEvents())
    .filter((e) => isUpcoming(e, today))
    .sort((a, b) => a.data.priority - b.data.priority || eventKey(a).localeCompare(eventKey(b)));
}

export async function getCompanyMap(): Promise<Map<string, Company>> {
  return new Map((await getPublishedCompanies()).map((c) => [c.id, c]));
}
