// Районы для фильтра «Где» (Афиша и Гид): деревни сводятся к районам, точное место остаётся на карточке.
import data from './regions.json';

const PLACES = data.places as Record<string, string>;
export const REGION_ORDER = data.regions;

/** Район для места из поля city. Нет города или место неизвестно (например, «Кипр») — undefined: запись видна только в «Везде». */
export function regionOf(place?: string): string | undefined {
  return place ? PLACES[place] : undefined;
}

/** Районы для фильтра: только те, где есть записи, по числу записей. */
export function regionOptions(places: (string | undefined)[]): string[] {
  const count = new Map<string, number>();
  for (const p of places) {
    const r = regionOf(p);
    if (r) count.set(r, (count.get(r) ?? 0) + 1);
  }
  return [...count.keys()].sort((a, b) => count.get(b)! - count.get(a)! || REGION_ORDER.indexOf(a) - REGION_ORDER.indexOf(b));
}
