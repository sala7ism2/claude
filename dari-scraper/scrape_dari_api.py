"""
Dari.ae directory scraper via its JSON API (fast route).

  python3 scrape_dari_api.py            # full run -> dari_agencies.csv (resumable)
  python3 scrape_dari_api.py --test     # just 2 list pages + 2 details, dumps samples

The page itself fetches an anonymous bearer token; we capture that request's headers
and reuse them for direct API calls. UNTESTED against the live API (sandbox is blocked),
so field names are handled generically; send me sample_list.json if anything looks off.
"""
import csv, json, os, sys, time
from playwright.sync_api import sync_playwright

PAGE = "https://www.dari.ae/en/app/directory?category=professions"
API = "https://api.dari.ae/property-service/api/v1/property"
SIZE = 100          # tries 100 per page; falls back to 12 if the API rejects it
DELAY = 0.4
RAW = "progress.jsonl"
OUT = "dari_agencies.csv"
TEST = "--test" in sys.argv


def flatten(o, prefix=""):
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(o, list):
        out[prefix[:-1]] = json.dumps(o, ensure_ascii=False) if o and isinstance(o[0], (dict, list)) \
            else "; ".join(map(str, o))
    else:
        out[prefix[:-1]] = o
    return out


def get_auth(pw):
    """Open the page, capture headers of the page's own authenticated API call."""
    br = pw.chromium.launch(headless=True)
    pg = br.new_page()
    box = {}
    def on_req(r):
        if "/property/profession" in r.url and r.headers.get("authorization"):
            box["h"] = {k: v for k, v in r.headers.items() if not k.startswith(":")}
    pg.on("request", on_req)
    pg.goto(PAGE, wait_until="networkidle")
    for _ in range(20):
        if "h" in box: break
        pg.wait_for_timeout(500)
    br.close()
    if "h" not in box:
        sys.exit("Could not capture auth header; run scrape_dari.py discover again.")
    return box["h"]


def items_of(j):
    """Find the list of records + total pages in a Spring-style or plain response."""
    if isinstance(j, list): return j, None
    for k in ("content", "data", "items", "result", "results", "records"):
        v = j.get(k)
        if isinstance(v, list): return v, j.get("totalPages")
        if isinstance(v, dict):
            r, t = items_of(v)
            if r: return r, t or j.get("totalPages")
    return [], None


def main():
    with sync_playwright() as pw:
        hdr = get_auth(pw)
        api = pw.request.new_context(extra_http_headers=hdr)

        def call(url):
            nonlocal hdr, api
            for attempt in range(4):
                r = api.get(url)
                if r.status == 401:          # token expired -> refresh
                    hdr = get_auth(pw); api = pw.request.new_context(extra_http_headers=hdr); continue
                if r.ok: return r.json()
                time.sleep(2 ** attempt)
            raise RuntimeError(f"{r.status} {url}")

        size = SIZE
        try:
            first = call(f"{API}/profession?page=0&size={size}")
            if len(items_of(first)[0]) <= 12: size = 12 if len(items_of(first)[0]) == 12 else size
        except RuntimeError:
            size = 12; first = call(f"{API}/profession?page=0&size={size}")
        json.dump(first, open("sample_list.json", "w"), indent=1, ensure_ascii=False)
        recs, total_pages = items_of(first)
        print(f"size={size}, first page has {len(recs)} records, totalPages={total_pages}")
        if not recs: sys.exit("No records found in sample_list.json - send it to me.")

        # 1) collect all list records
        listing, p = list(recs), 1
        while (total_pages is None or p < total_pages) and not (TEST and p >= 2):
            recs, tp = items_of(call(f"{API}/profession?page={p}&size={size}"))
            if not recs: break
            listing += recs; p += 1; time.sleep(DELAY)
            if p % 10 == 0: print(f"list page {p}/{total_pages}")
        print("list records:", len(listing))

        # 2) detail per record (resume-safe)
        done = set()
        if os.path.exists(RAW):
            done = {json.loads(l)["_id"] for l in open(RAW, encoding="utf-8")}
        out = open(RAW, "a", encoding="utf-8")
        todo = [r for r in listing if str(r.get("id")) not in done]
        for i, r in enumerate(todo[:2] if TEST else todo, 1):
            rid = r.get("id")
            try:
                d = call(f"{API}/professionByLicense?id={rid}")
            except Exception as e:
                d = {"error": str(e)}
            if TEST and i == 1: json.dump(d, open("sample_detail.json", "w"), indent=1, ensure_ascii=False)
            row = {**flatten(r, "list."), **flatten(d, "detail."), "_id": str(rid)}
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
            if i % 50 == 0: print(f"detail {i}/{len(todo)}")
            time.sleep(DELAY)
        out.close()

    rows = [json.loads(l) for l in open(RAW, encoding="utf-8")]
    cols = sorted({k for r in rows for k in r})
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f"saved {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
