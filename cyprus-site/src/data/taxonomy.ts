// Разделы «Гида» и их подкатегории.
// Источник: Google Sheet «Сайт Кипра — бэклог…», вкладки «Разделы сайта» и «Карта категорий» (12.11.2026).
// `sourceCategories` — названия категорий во внутренней базе (колонка 2), используются импортом.

export interface Category {
  slug: string;
  title: string;
  sourceCategories: string[];
}

export interface Section {
  slug: string;
  title: string;
  intro: string;
  categories: Category[];
}

export const SECTIONS: Section[] = [
  {
    slug: 'cars',
    title: 'Автомобили',
    intro: 'Заказ автомобилей из Японии, автоподбор, новые автомобили и аренда.',
    categories: [
      { slug: 'japan-import', title: 'Заказ из Японии', sourceCategories: ['Автомобили'] },
      { slug: 'car-selection', title: 'Автоподбор', sourceCategories: [] },
      { slug: 'new-cars', title: 'Новые авто', sourceCategories: [] },
      { slug: 'car-rental', title: 'Аренда авто', sourceCategories: [] },
    ],
  },
  {
    slug: 'education',
    title: 'Образование',
    intro: 'Частные школы и курсы греческого языка.',
    categories: [
      { slug: 'private-schools', title: 'Частные школы', sourceCategories: ['Частные школы'] },
      { slug: 'greek', title: 'Греческий язык', sourceCategories: ['Греческий язык'] },
    ],
  },
  {
    slug: 'property-home',
    title: 'Недвижимость и дом',
    intro: 'Застройщики, агентства, ипотека, юридическое сопровождение и ремонт.',
    categories: [
      { slug: 'real-estate', title: 'Застройщики и агентства', sourceCategories: ['Недвижимость'] },
      { slug: 'mortgage', title: 'Ипотека и финансы', sourceCategories: ['Ипотека и финансы'] },
      { slug: 'legal', title: 'Юридические услуги', sourceCategories: ['Юридические услуги'] },
      { slug: 'home-repair', title: 'Дом и ремонт', sourceCategories: ['Дом и ремонт'] },
    ],
  },
  {
    slug: 'hotels-spa',
    title: 'Отели и SPA',
    intro: 'Отели и курорты, бани, хаммамы и SPA.',
    categories: [
      { slug: 'hotels', title: 'Отели и размещение', sourceCategories: ['Отели и размещение'] },
      { slug: 'spa', title: 'Бани и SPA', sourceCategories: ['Бани и SPA'] },
    ],
  },
  {
    slug: 'health-beauty',
    title: 'Здоровье и красота',
    intro: 'Медицина и стоматология, тату-студии и удаление татуировок.',
    categories: [
      { slug: 'medical', title: 'Медицина и стоматология', sourceCategories: ['Медицина и здоровье'] },
      { slug: 'tattoo', title: 'Тату и удаление тату', sourceCategories: ['Красота и здоровье'] },
    ],
  },
  {
    slug: 'food',
    title: 'Кафе и рестораны',
    intro: 'Кафе и рестораны Кипра.',
    categories: [{ slug: 'cafes', title: 'Кафе и рестораны', sourceCategories: ['Кафе и рестораны'] }],
  },
  {
    slug: 'entertainment',
    title: 'Досуг и развлечения',
    intro: 'Аренда лодок и яхт, кино и развлечения, организаторы и площадки, билетные сервисы. Сами мероприятия — в «Афише».',
    categories: [
      { slug: 'boats', title: 'Аренда лодок и яхт', sourceCategories: ['Аренда лодок'] },
      { slug: 'cinema', title: 'Кино и развлечения', sourceCategories: ['Кино и развлечения'] },
      { slug: 'organizers', title: 'Организаторы и площадки', sourceCategories: ['События и досуг'] },
      { slug: 'tickets', title: 'Билетные сервисы', sourceCategories: ['Билеты и афиша'] },
    ],
  },
  {
    slug: 'other',
    title: 'Другие сервисы',
    intro: 'Спорт и фитнес, магазины, цветы и другое.',
    categories: [
      { slug: 'sport', title: 'Спорт и фитнес', sourceCategories: ['Спорт и фитнес', 'Спорт и досуг'] },
      { slug: 'shops', title: 'Магазины', sourceCategories: ['Магазины'] },
      { slug: 'flowers', title: 'Цветы и подарки', sourceCategories: ['Цветы и подарки'] },
    ],
  },
];

export const SECTION_SLUGS = SECTIONS.map((s) => s.slug) as [string, ...string[]];
export const CATEGORY_SLUGS = SECTIONS.flatMap((s) => s.categories.map((c) => c.slug)) as [string, ...string[]];

export function getSection(slug: string): Section | undefined {
  return SECTIONS.find((s) => s.slug === slug);
}

export function getCategory(slug: string): (Category & { section: Section }) | undefined {
  for (const section of SECTIONS) {
    const c = section.categories.find((c) => c.slug === slug);
    if (c) return { ...c, section };
  }
  return undefined;
}

/** Названия подкатегорий в порядке таксономии (как в фильтре раздела). */
export function categoryTitles(slugs: string[]): string[] {
  const order = CATEGORY_SLUGS as readonly string[];
  return [...new Set(slugs)].sort((a, b) => order.indexOf(a) - order.indexOf(b)).map((s) => getCategory(s)?.title).filter((t): t is string => !!t);
}

// Типы мероприятий для «Афиши».
export const EVENT_TYPES = {
  concert: 'Концерт',
  theatre: 'Театр и шоу',
  standup: 'Стендап',
  festival: 'Фестиваль',
  exhibition: 'Выставка',
  cinema: 'Кино',
  kids: 'Детям',
  sport: 'Спорт',
  party: 'Вечеринка',
  tour: 'Экскурсия и прогулка',
  workshop: 'Мастер-класс',
  talk: 'Лекция и встреча',
  other: 'Другое',
} as const;

export type EventType = keyof typeof EVENT_TYPES;
export const EVENT_TYPE_SLUGS = Object.keys(EVENT_TYPES) as [EventType, ...EventType[]];
