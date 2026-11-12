/**
 * Приём заявок «Добавить компанию».
 *  - Каждая заявка приходит письмом владельцу скрипта (тому Google-аккаунту, от имени которого он развёрнут).
 *    Адрес нигде не прописан и не виден на сайте.
 *  - Если скрипт создан внутри Google-таблицы (Расширения → Apps Script), заявка дополнительно
 *    записывается строкой на лист «Заявки компаний». Если скрипт отдельный — только письмо.
 * Установка — см. docs/forms/README.md.
 */
const SHEET_NAME = 'Заявки компаний';
const SECTIONS = {
  'cars': 'Автомобили', 'education': 'Образование', 'property-home': 'Недвижимость и дом',
  'leisure-spa': 'Отдых и SPA', 'health-beauty': 'Здоровье и красота', 'food': 'Кафе и рестораны',
  'entertainment': 'События и развлечения', 'other': 'Другие сервисы',
};
const FIELDS = [
  ['name', 'Компания'], ['section', 'Раздел'], ['about', 'Чем занимается'], ['city', 'Город'],
  ['website', 'Сайт'], ['person', 'Имя'], ['contact', 'Контакт'], ['ads_interest', 'Реклама интересует'],
  ['consent', 'Согласие'], ['page', 'Страница'],
];

function doPost(e) {
  let data;
  try { data = JSON.parse(e.postData.contents); } catch (err) { return out('bad request'); }
  if (data.website_hp) return out('ok'); // ловушка для ботов заполнена — молча игнорируем
  if (!data.name || !data.website || !data.contact) return out('bad request');

  data.section = SECTIONS[data.section] || data.section;
  data.ads_interest = data.ads_interest === 'yes' ? 'да' : 'нет';
  data.consent = data.consent === 'yes' ? 'да' : 'нет';

  sendEmail(data);
  saveToSheet(data);
  return out('ok');
}

function sendEmail(data) {
  const to = Session.getEffectiveUser().getEmail();
  const lines = FIELDS.map(([key, label]) => label + ': ' + text(data[key]));
  const options = { name: 'Гид по Кипру — заявки' };
  // Если заявитель оставил email, «Ответить» в почте сразу пойдёт ему.
  const email = String(data.contact || '').match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
  if (email) options.replyTo = email[0];
  MailApp.sendEmail(to, 'Заявка в гид: ' + text(data.name).slice(0, 80),
    'Новая заявка на добавление компании.\n\n' + lines.join('\n') +
    '\n\nПеред публикацией проверьте данные по официальному сайту.', options);
}

function saveToSheet(data) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) return; // скрипт создан отдельно от таблицы — только письмо
  const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) sheet.appendRow(['Получено'].concat(FIELDS.map((f) => f[1]), ['Статус']));
  sheet.appendRow([new Date()].concat(FIELDS.map(([key]) => cell(data[key])), ['Новая']));
}

function text(v) { return String(v == null ? '' : v).slice(0, 1000); }

// В ячейке таблицы защищаемся от формул (=, +, -, @ в начале строки).
function cell(v) {
  const s = text(v);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function out(t) {
  return ContentService.createTextOutput(t).setMimeType(ContentService.MimeType.TEXT);
}
