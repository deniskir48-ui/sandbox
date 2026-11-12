// Общие настройки сайта. Название и домен ещё НЕ выбраны (см. DECISIONS.md, DEC-W02).
export const SITE = {
  // Временное техническое название. Меняется здесь в одном месте.
  name: 'Гид по Кипру',
  tagline: 'Компании, мероприятия и практические статьи для русскоязычных жителей Кипра',
  // Адрес сайта задаётся переменной окружения SITE_URL при сборке (нужен для sitemap и canonical).
  url: process.env.SITE_URL || '',
  locale: 'ru',
  timeZone: 'Europe/Nicosia',
};

export const NAV = [
  { href: '/catalog/', label: 'Гид' },
  { href: '/events/', label: 'Афиша' },
  { href: '/guides/', label: 'Статьи' },
  { href: '/about/', label: 'О проекте' },
];

// Читается при сборке (весь код страниц выполняется на этапе build, в браузер не попадает).
export const USE_FIXTURES = process.env.USE_FIXTURES === '1';
