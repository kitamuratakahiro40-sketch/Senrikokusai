/**
 * 編入チャレンジ — 採点・面接の履歴をこのスプレッドシートに1行ずつ記録するスクリプト。
 * Google スプレッドシートの [拡張機能] → [Apps Script] に、この内容を丸ごと貼り付けて使います。
 * 設定の手順は「スプレッドシート設定手順.md」を参照してください。
 */

// 表の見出し（左から）と、アプリから届くデータのキー（順番を合わせる）
var HEADERS = ['日時', '種別', '言語', 'お題・質問', '回答', '点数', '評価', 'コメント', '詳細'];
var KEYS    = ['datetime', 'type', 'lang', 'topic', 'answer', 'score', 'grade', 'comment', 'detail'];

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];

    // まだ何も無ければ見出し行を作る
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);
      sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
      sheet.setFrozenRows(1);
    }

    var row = KEYS.map(function (k) {
      return (data[k] !== undefined && data[k] !== null) ? data[k] : '';
    });
    sheet.appendRow(row);

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
