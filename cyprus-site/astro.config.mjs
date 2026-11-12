import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// SITE_URL задаётся при сборке (например, https://example.cy). Пока домен не выбран,
// sitemap не генерируется: карта сайта с неверным доменом хуже, чем её отсутствие.
const site = process.env.SITE_URL || undefined;

export default defineConfig({
  site,
  trailingSlash: 'always',
  integrations: site ? [sitemap({ filter: (page) => !page.includes('/search/') })] : [],
  build: { format: 'directory' },
});
