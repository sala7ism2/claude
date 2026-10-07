"""
Daily sync: find agencies on Dari that are not yet in the Google Sheet and append them.

Env vars:
  SHEET_ID        Google Sheet id (the long string in its URL)
  GOOGLE_SA_JSON  service-account key JSON (the sheet must be shared with its client_email as Editor)
  SHEET_TAB       optional, default first tab
The sheet's header row must contain an `_id` column (kept from dari_agencies.csv), plus
optional `first_seen` and `notified` columns (added automatically if missing).
"""
import datetime, json, os, sys, time
import gspread
from playwright.sync_api import sync_playwright
from scrape_dari_api import API, get_auth, items_of, flatten

SIZE, DELAY = 12, 0.4


def main():
    gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SA_JSON"]))
    sh = gc.open_by_key(os.environ["SHEET_ID"])
    ws = sh.worksheet(os.environ["SHEET_TAB"]) if os.environ.get("SHEET_TAB") else sh.sheet1
    header = ws.row_values(1)
    for extra in ("first_seen", "notified"):
        if extra not in header:
            header.append(extra); ws.update_cell(1, len(header), extra)
    known = set(ws.col_values(header.index("_id") + 1)[1:])
    print("agencies already in sheet:", len(known))

    with sync_playwright() as pw:
        hdr = get_auth(pw); api = pw.request.new_context(extra_http_headers=hdr)

        def call(url):
            nonlocal hdr, api
            for a in range(4):
                r = api.get(url)
                if r.status == 401:
                    hdr = get_auth(pw); api = pw.request.new_context(extra_http_headers=hdr); continue
                if r.ok: return r.json()
                time.sleep(2 ** a)
            raise RuntimeError(f"{r.status} {url}")

        listing, p, total = [], 0, None
        while total is None or p < total:
            recs, tp = items_of(call(f"{API}/profession?page={p}&size={SIZE}"))
            total = tp or total or 1
            if not recs: break
            listing += recs; p += 1; time.sleep(0.2)
        if len(listing) < 0.9 * len(known):      # sanity: never act on a truncated crawl
            sys.exit(f"Only {len(listing)} listed vs {len(known)} known - aborting, nothing written.")
        new = [r for r in listing if str(r.get("id")) not in known]
        print(f"listed {len(listing)}, new {len(new)}")

        rows = []
        today = datetime.date.today().isoformat()
        for r in new:
            d = call(f"{API}/professionByLicense?id={r.get('id')}")
            flat = {**flatten(r, "list."), **flatten(d, "detail."), "_id": str(r.get("id")), "first_seen": today}
            rows.append([flat.get(h, "") for h in header]); time.sleep(DELAY)

    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    print("appended", len(rows))


if __name__ == "__main__":
    main()
