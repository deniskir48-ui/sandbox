// Районы для фильтра «Где» (Афиша и Гид): деревни и составные строки сводятся к районам, точное место остаётся на карточке.
// Правила — в src/data/regions.json. ВСЕ_КИПР ('*') — запись видна при выборе любого района.
import data from './regions.json';

const PLACES = data.places as Record<string, string>;
const KEYWORDS = data.keywords as [string, string][];
export const UNKNOWN_REGION = data.unknown;
export const ALL_CYPRUS = '*';
export const REGION_ORDER = [...data.regions, data.unknown];

/** Районы для места из поля city. [] — место не распознано (запись видна только в «Везде»). */
export function regionsOf(place?: string): string[] {
  if (!place) return [];
  if (PLACES[place]) return [PLACES[place]];
  const low = place.toLowerCase();
  const out = new Set<string>();
  // «Неизвестно» — только для места целиком «Кипр»; часть «Кипр» в «Кипр, онлайн» ничего не значит.
  for (const part of place.split(/\s*(?:[,;/]|\sи\s)\s*/)) if (PLACES[part] && PLACES[part] !== UNKNOWN_REGION) out.add(PLACES[part]);
  for (const [kw, region] of KEYWORDS) if (low.includes(kw)) out.add(region);
  if (data.everywhere.some((w) => low.includes(w))) out.add(ALL_CYPRUS);
  return [...out];
}

/** Значение data-city для карточки: районы через «|». */
export const regionAttr = (place?: string) => regionsOf(place).join('|');

/** Районы для фильтра: только те, где есть записи, по числу записей; «Неизвестно» — в конце. */
export function regionOptions(places: (string | undefined)[]): string[] {
  const count = new Map<string, number>();
  for (const p of places) for (const r of regionsOf(p)) if (r !== ALL_CYPRUS) count.set(r, (count.get(r) ?? 0) + 1);
  return [...count.keys()].sort((a, b) =>
    Number(a === UNKNOWN_REGION) - Number(b === UNKNOWN_REGION) || count.get(b)! - count.get(a)! || REGION_ORDER.indexOf(a) - REGION_ORDER.indexOf(b));
}
