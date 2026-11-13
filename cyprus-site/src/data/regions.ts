// Районы для фильтра «Где» (Афиша и Гид): деревни сводятся к районам, точное место остаётся на карточке.
import data from './regions.json';

const PLACES = data.places as Record<string, string>;
export const OTHER_REGION = data.other;
export const REGION_ORDER = [...data.regions, data.other];

/** Район для места из поля city. Пусто — нет города; неизвестное место — «Другие места». */
export function regionOf(place?: string): string | undefined {
  if (!place) return undefined;
  return PLACES[place] ?? OTHER_REGION;
}

/** Районы для фильтра: по числу записей, «Другие места» — в конце. */
export function regionOptions(places: (string | undefined)[]): string[] {
  const count = new Map<string, number>();
  for (const p of places) {
    const r = regionOf(p);
    if (r) count.set(r, (count.get(r) ?? 0) + 1);
  }
  return [...count.keys()].sort((a, b) =>
    Number(a === OTHER_REGION) - Number(b === OTHER_REGION) || count.get(b)! - count.get(a)! || REGION_ORDER.indexOf(a) - REGION_ORDER.indexOf(b));
}
