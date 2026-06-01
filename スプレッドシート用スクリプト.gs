/**
 * 編入チャレンジ — 採点・面接の履歴をこのスプレッドシートに1行ずつ記録するスクリプト。
 * Google スプレッドシートの [拡張機能] → [Apps Script] に、この内容を丸ごと貼り付けて使います。
 * 設定の手順は「スプレッドシート設定手順.md」を参照してください。
 */

// 表の見出し（左から）と、アプリから届くデータのキー（順番を合わせる）
var HEADERS = ['日時', '種別', '言語', 'お題・質問', '回答', '点数', '評価', 'コメント', '詳細', '模範回答'];
var KEYS    = ['datetime', 'type', 'lang', 'topic', 'answer', 'score', 'grade', 'comment', 'detail', 'model_answer'];

function ensureHeaders(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  } else {
    var current = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), HEADERS.length)).getValues()[0];
    HEADERS.forEach(function (h, i) {
      if (current[i] !== h) sheet.getRange(1, i + 1).setValue(h).setFontWeight('bold');
    });
  }
  sheet.getRange(1, 1, sheet.getMaxRows(), HEADERS.length)
    .setWrap(true)
    .setVerticalAlignment('top');
}

function updateModelAnswer(sheet, data) {
  ensureHeaders(sheet);
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;
  var rows = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
  for (var i = rows.length - 1; i >= 0; i--) {
    var topic = rows[i][3];
    var answer = rows[i][4];
    if (topic === data.topic && answer === data.answer) {
      sheet.getRange(i + 2, HEADERS.length).setValue(data.model_answer || '')
        .setWrap(true)
        .setVerticalAlignment('top');
      return true;
    }
  }
  return false;
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    if (data.action === 'update_model_answer') {
      return ContentService
        .createTextOutput(JSON.stringify({ ok: true, updated: updateModelAnswer(sheet, data) }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // まだ何も無ければ見出し行を作る
    ensureHeaders(sheet);

    var row = KEYS.map(function (k) {
      return (data[k] !== undefined && data[k] !== null) ? data[k] : '';
    });
    sheet.appendRow(row);
    // 追記した行も折り返し＋上揃えに
    sheet.getRange(sheet.getLastRow(), 1, 1, HEADERS.length)
      .setWrap(true)
      .setVerticalAlignment('top');

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ブラウザでURLを開いたときの確認用（任意）
function doGet(e) {
  return ContentService.createTextOutput('OK — 編入チャレンジ ログ受け口は動いています。');
}
