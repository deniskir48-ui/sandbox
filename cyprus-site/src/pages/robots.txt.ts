import type { APIRoute } from 'astro';
// Пока домен не задан (SITE_URL), запрещаем индексацию: это черновая сборка.
export const GET: APIRoute = ({ site }) => {
  const body = site
    ? `User-agent: *\nAllow: /\nDisallow: /search/\n\nSitemap: ${new URL('sitemap-index.xml', site).href}\n`
    : `User-agent: *\nDisallow: /\n`;
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
