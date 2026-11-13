// Районы для фильтра «Где» (Афиша и Гид): деревни сводятся к районам, точное место остаётся на карточке.
import data from './regions.json';

const PLACES = data.places as Record<string, string>;
export const UNKNOWN_REGION = data.unknown;
export const REGION_ORDER = [...data.regions, data.unknown];

/** Район для места из поля city. «Кипр» без точного места — «Неизвестно». Места нет в справочнике — undefined: запись видна только в «Везде». */
export function regionOf(place?: string): string | undefined {
  return place ? PLACES[place] : undefined;
}

/** Районы для фильтра: только те, где есть записи, по числу записей; «Неизвестно» — в конце. */
export function regionOptions(places: (string | undefined)[]): string[] {
  const count = new Map<string, number>();
  for (const p of places) {
    const r = regionOf(p);
    if (r) count.set(r, (count.get(r) ?? 0) + 1);
  }
  return [...count.keys()].sort((a, b) =>
    Number(a === UNKNOWN_REGION) - Number(b === UNKNOWN_REGION) || count.get(b)! - count.get(a)! || REGION_ORDER.indexOf(a) - REGION_ORDER.indexOf(b));
}
