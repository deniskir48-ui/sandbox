/**
 * Приём заявок «Добавить компанию» в Google-таблицу.
 * Установка — см. docs/forms/README.md.
 */
const SHEET_NAME = 'Заявки компаний';
const HEADERS = ['Получено', 'Компания', 'Раздел', 'Чем занимается', 'Город', 'Сайт', 'Имя', 'Контакт',
                 'Реклама интересует', 'Согласие', 'Страница', 'Статус'];

function doPost(e) {
  let data;
  try { data = JSON.parse(e.postData.contents); } catch (err) { return out('bad request'); }
  if (data.website_hp) return out('ok'); // ловушка для ботов заполнена — молча игнорируем

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) sheet.appendRow(HEADERS);

  sheet.appendRow([
    new Date(), clean(data.name), clean(data.section), clean(data.about), clean(data.city),
    clean(data.website), clean(data.person), clean(data.contact),
    data.ads_interest === 'yes' ? 'да' : '', data.consent === 'yes' ? 'да' : 'нет',
    clean(data.page), 'Новая',
  ]);
  return out('ok');
}

// Обрезаем длину и защищаемся от формул в ячейках (=, +, -, @ в начале строки).
function clean(v) {
  let s = String(v == null ? '' : v).slice(0, 1000);
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return s;
}

function out(text) {
  return ContentService.createTextOutput(text).setMimeType(ContentService.MimeType.TEXT);
}
