// Paste into the Sheet: Extensions > Apps Script. Then Triggers > Add trigger >
// notifyNewAgencies > Time-driven > Day timer > 8-9am (after the 08:00 sync).
const EMAIL = "sala7ism@gmail.com";
const SHOW = ["detail.name", "detail.nameEn", "list.name", "list.nameEn", "detail.phone", "detail.email", "detail.licenseNumber"]; // edit to your real column names

function notifyNewAgencies() {
  const ws = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  const data = ws.getDataRange().getValues();
  const h = data[0], fs = h.indexOf("first_seen"), nt = h.indexOf("notified");
  const cols = SHOW.map(c => h.indexOf(c)).filter(i => i >= 0);
  const lines = [], mark = [];
  for (let r = 1; r < data.length; r++) {
    if (data[r][fs] && !data[r][nt]) {
      lines.push(cols.map(i => data[r][i]).join(" | ")); mark.push(r + 1);
    }
  }
  if (!lines.length) return;
  MailApp.sendEmail(EMAIL, `Dari: ${lines.length} new real estate agencies`,
    lines.join("\n") + "\n\nSheet: " + SpreadsheetApp.getActiveSpreadsheet().getUrl());
  mark.forEach(r => ws.getRange(r, nt + 1).setValue("yes"));
}
