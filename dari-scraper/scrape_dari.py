"""
Dari.ae directory scraper (Playwright).

Run on YOUR machine (this cloud sandbox blocks dari.ae).
  pip install playwright && playwright install chromium
  python scrape_dari.py discover   # step 1: see which JSON APIs the site calls
  python scrape_dari.py scrape     # step 2: crawl all pages -> dari_agencies.csv

UNTESTED against the live site: selectors are generic and will likely need one tweak.
"""
import csv, json, re, sys, time
from playwright.sync_api import sync_playwright

URL = "https://www.dari.ae/en/app/directory?category=professions"
OUT = "dari_agencies.csv"
DELAY = 1.5  # seconds between requests: be polite, avoid blocks


def discover():
    """Log every JSON response so you can find the real API (best route: call it directly)."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)
        pg = b.new_page()
        pg.on("response", lambda r: print(r.status, r.url)
              if "json" in (r.headers.get("content-type") or "") else None)
        pg.goto(URL, wait_until="networkidle")
        input("Click page 2 / open one agency, watch the log, then press Enter...")
        b.close()


def kv_from_page(pg):
    """Generic extraction: grab label/value pairs + mailto/tel links from a detail page."""
    data = {"url": pg.url, "title": pg.title()}
    text = pg.inner_text("body")
    for m in re.finditer(r"^([A-Za-z][\w /&.-]{2,40})\s*[:\n]\s*(.+)$", text, re.M):
        data.setdefault(m.group(1).strip(), m.group(2).strip())
    data["emails"] = ";".join({a.get_attribute("href")[7:] for a in pg.query_selector_all("a[href^='mailto:']")})
    data["phones"] = ";".join({a.get_attribute("href")[4:] for a in pg.query_selector_all("a[href^='tel:']")})
    return data


def scrape():
    rows, seen = [], set()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context()
        lst = ctx.new_page()
        lst.goto(URL, wait_until="networkidle")
        page_no = 1
        while True:
            # >>> adjust selector: the card/link that opens an agency
            links = lst.eval_on_selector_all(
                "a[href*='/directory/'], a[href*='professions']", "els=>els.map(e=>e.href)")
            new = [l for l in dict.fromkeys(links) if l not in seen and l != URL]
            for href in new:
                seen.add(href)
                d = ctx.new_page()
                try:
                    d.goto(href, wait_until="networkidle")
                    rows.append(kv_from_page(d))
                except Exception as e:
                    rows.append({"url": href, "error": str(e)})
                d.close()
                time.sleep(DELAY)
            print(f"page {page_no}: {len(new)} new, {len(rows)} total")
            # >>> adjust selector: the "next page" button
            nxt = lst.query_selector("button[aria-label*='Next' i]:not([disabled]), a[rel=next]")
            if not nxt or not new:
                break
            nxt.click(); lst.wait_for_load_state("networkidle"); page_no += 1
            time.sleep(DELAY)
            json.dump(rows, open("progress.json", "w"))  # checkpoint
        b.close()
    cols = list({k for r in rows for k in r})
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print("saved", OUT)


if __name__ == "__main__":
    {"discover": discover, "scrape": scrape}[sys.argv[1] if len(sys.argv) > 1 else "scrape"]()
