import type { APIRoute } from 'astro';
import { getPublishedCompanies, getUpcomingEvents, getPublishedArticles, categoriesOf } from '../lib/data';
import { getCategory, categoryTitles, EVENT_TYPES } from '../data/taxonomy';
import { formatEventWhen } from '../lib/dates';

// Статический индекс для поиска: только опубликованные записи и только публичные поля.
export const GET: APIRoute = async () => {
  const companies = (await getPublishedCompanies()).map((c) => {
    const cat = getCategory(c.data.category)!;
    return {
      kind: 'company', url: `/services/${c.id}/`, title: c.data.name,
      meta: [cat.section.title, categoryTitles(categoriesOf(c)).join(', '), c.data.city].filter(Boolean).join(' · '),
      text: [c.data.service_type, c.data.summary, c.data.description, c.data.network, ...c.data.services].filter(Boolean).join(' '),
    };
  });
  const events = (await getUpcomingEvents()).map((e) => ({
    kind: 'event', url: `/events/${e.id}/`, title: e.data.title,
    meta: [EVENT_TYPES[e.data.type], formatEventWhen(e.data.date, e.data.time, e.data.end_date), e.data.city].join(' · '),
    text: [e.data.summary, e.data.venue].filter(Boolean).join(' '),
    end: e.data.end_date ?? e.data.date,
  }));
  const articles = (await getPublishedArticles()).map((a) => ({
    kind: 'article', url: `/guides/${a.id}/`, title: a.data.title, meta: 'Статья', text: a.data.description,
  }));
  return new Response(JSON.stringify([...companies, ...events, ...articles]), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};
