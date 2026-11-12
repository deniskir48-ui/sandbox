// Клиентская фильтрация статических списков. Состояние фильтров хранится в URL (?city=...&type=...),
// поэтому отфильтрованной ссылкой можно поделиться.
type Values = Record<string, string>;

interface Options {
  form: string;
  items: string;
  count?: string;
  empty?: string;
  match: (el: HTMLElement, f: Values) => boolean;
}

export function bindFilters(o: Options) {
  const form = document.querySelector<HTMLFormElement>(o.form);
  const items = [...document.querySelectorAll<HTMLElement>(o.items)];
  const count = o.count ? document.querySelector<HTMLElement>(o.count) : null;
  const empty = o.empty ? document.querySelector<HTMLElement>(o.empty) : null;

  const read = (): Values => {
    const v: Values = {};
    if (form) new FormData(form).forEach((val, key) => (v[key] = String(val)));
    return v;
  };

  const apply = (updateUrl = true) => {
    const f = read();
    let shown = 0;
    for (const el of items) {
      const ok = o.match(el, f);
      el.hidden = !ok;
      if (ok) shown++;
    }
    if (count) count.textContent = `Найдено: ${shown}`;
    if (empty) empty.hidden = shown > 0;
    if (updateUrl && form) {
      const url = new URL(location.href);
      for (const [k, val] of Object.entries(f)) val ? url.searchParams.set(k, val) : url.searchParams.delete(k);
      history.replaceState(null, '', url);
    }
  };

  if (form) {
    // Восстанавливаем фильтры из URL.
    const params = new URLSearchParams(location.search);
    for (const el of [...form.elements] as HTMLSelectElement[]) {
      const val = el.name && params.get(el.name);
      if (val && [...(el.options ?? [])].some((opt) => opt.value === val)) el.value = val;
    }
    form.addEventListener('change', () => apply());
    form.addEventListener('submit', (e) => e.preventDefault());
  }
  apply(false);
}

/** Сегодня на Кипре, ГГГГ-ММ-ДД (в браузере). */
export function todayCyprus(offsetDays = 0): string {
  const d = new Date(Date.now() + offsetDays * 86400000);
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Nicosia', year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
}
