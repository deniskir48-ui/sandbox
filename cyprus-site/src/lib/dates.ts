const TZ = 'Europe/Nicosia';

/** Сегодняшняя дата на Кипре в формате ГГГГ-ММ-ДД. */
export function todayInCyprus(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}

const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

/** «20 ноября 2026, пт» из строки ГГГГ-ММ-ДД (без сдвигов часовых поясов). */
export function formatDay(iso: string, withWeekday = true): string {
  const [y, m, d] = iso.split('-').map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${d} ${MONTHS[m - 1]} ${y}${withWeekday ? `, ${WEEKDAYS[wd]}` : ''}`;
}

export function formatEventWhen(date: string, time?: string, endDate?: string): string {
  if (endDate && endDate !== date) return `${formatDay(date, false)} — ${formatDay(endDate, false)}`;
  return time ? `${formatDay(date)}, ${time}` : formatDay(date);
}

export function formatDate(d: Date): string {
  return formatDay(d.toISOString().slice(0, 10), false);
}

export const isoDate = (d: Date) => d.toISOString().slice(0, 10);

const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const WEEKDAYS_FULL = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

/** Части «корешка» карточки события: «14–15» / «ноя» / «сб–вс» и подпись для текста. */
export function stubParts(date: string, endDate?: string) {
  const [y, m, d] = date.split('-').map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  if (endDate && endDate !== date) {
    const [y2, m2, d2] = endDate.split('-').map(Number);
    const wd2 = new Date(Date.UTC(y2, m2 - 1, d2)).getUTCDay();
    const sameMonth = m === m2;
    return {
      day: sameMonth ? `${d}–${d2}` : `${d}`,
      month: sameMonth ? MONTHS_SHORT[m - 1] : `${MONTHS_SHORT[m - 1]}–${MONTHS_SHORT[m2 - 1]}`,
      weekday: `${WEEKDAYS_FULL[wd]}–${WEEKDAYS_FULL[wd2]}`,
      label: formatEventWhen(date, undefined, endDate),
    };
  }
  return { day: `${d}`, month: MONTHS_SHORT[m - 1], weekday: WEEKDAYS_FULL[wd], label: formatDay(date) };
}
