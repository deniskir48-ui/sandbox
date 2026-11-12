import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
import { CATEGORY_SLUGS, EVENT_TYPE_SLUGS, SECTION_SLUGS } from './data/taxonomy';

// В режиме USE_FIXTURES=1 данные берутся из /fixtures (технические тестовые записи).
// Продакшен-сборка их не видит вообще.
const root = process.env.USE_FIXTURES === '1' ? './fixtures' : './src/content';

const source = z.object({ title: z.string(), url: z.string().url() });

// Шлюз публикации: запись становится видимой только со status: published
// и только если заполнены обязательные проверенные поля.
function publishGate<T extends { status: string }>(required: (keyof T)[]) {
  return (data: T, ctx: z.RefinementCtx) => {
    if (data.status !== 'published') return;
    for (const key of required) {
      const v = data[key] as unknown;
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `Для публикации обязательно поле «${String(key)}»` });
      }
    }
  };
}

const companies = defineCollection({
  loader: glob({ pattern: '**/*.{yaml,yml}', base: `${root}/companies` }),
  schema: z
    .object({
      name: z.string(),
      status: z.enum(['draft', 'published']).default('draft'),
      section: z.enum(SECTION_SLUGS),
      category: z.enum(CATEGORY_SLUGS),
      city: z.string().optional(), // город/регион, только подтверждённый
      network: z.string().optional(), // сеть, если это филиал/кампус
      service_type: z.string().optional(), // тип услуги: «Застройщик», «Баня на дровах»
      languages: z.string().optional(), // языки обучения/обслуживания: «EN/EL»
      summary: z.string().max(160).optional(), // для списка, до ~150 символов
      description: z.string().optional(), // описание услуг для подробной страницы
      website: z.string().url().optional(), // официальный сайт
      channel: z.object({ label: z.string(), url: z.string().url() }).optional(), // официальный публичный канал
      sources: z.array(source).default([]),
      verified_at: z.coerce.date().optional(),
      source_id: z.string().optional(), // ID во внутренней базе, на сайте не показывается
    })
    .superRefine(publishGate(['summary', 'sources', 'verified_at'])),
});

const events = defineCollection({
  loader: glob({ pattern: '**/*.{yaml,yml}', base: `${root}/events` }),
  schema: z
    .object({
      title: z.string(),
      status: z.enum(['draft', 'published']).default('draft'),
      type: z.enum(EVENT_TYPE_SLUGS),
      // Приоритет редактора: 1 — в первую очередь, 2 — интересно, 3 — дополнительно. Определяет порядок в Афише.
      priority: z.number().int().min(1).max(5).default(3),
      date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Формат даты: ГГГГ-ММ-ДД'),
      time: z.string().regex(/^\d{2}:\d{2}$/, 'Формат времени: ЧЧ:ММ').optional(),
      end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(), // для многодневных событий
      city: z.string(),
      venue: z.string().optional(),
      summary: z.string().max(200).optional(),
      description: z.string().optional(),
      ticket_url: z.string().url().optional(), // билеты или официальная страница
      price: z.string().optional(), // только проверенная цена, например «€25–40»
      organizer: z.string().optional(), // slug компании из Гида
      sources: z.array(source).default([]),
      verified_at: z.coerce.date().optional(),
    })
    .superRefine(publishGate(['summary', 'ticket_url', 'sources'])), // события проверяются при составлении недельной таблицы
});

const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: `${root}/articles` }),
  schema: z
    .object({
      title: z.string(),
      description: z.string().max(200),
      status: z.enum(['draft', 'published']).default('draft'),
      published_at: z.coerce.date(),
      updated_at: z.coerce.date().optional(),
      section: z.enum(SECTION_SLUGS).optional(),
      companies: z.array(z.string()).default([]), // slugs компаний из Гида
      sources: z.array(source).default([]),
    }),
});

export const collections = { companies, events, articles };
