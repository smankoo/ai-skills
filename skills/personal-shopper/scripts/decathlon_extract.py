#!/usr/bin/env python3
"""
decathlon_extract.py — Decathlon CA (decathlon.ca) product extractor.

WHY THIS EXISTS
  decathlon.ca is HARD Cloudflare-walled from the VPS: curl / requests / web_extract
  all get "Just a moment..." (403). No public JSON API, no Shopify, no `.json`.
  Must be run through a REAL windowed Chrome on the Mac over CDP (rung 3 of the
  bot-wall-bypass ladder). NOT headless — headless UA gets flagged.

HOW TO RUN (on Sumeet's Mac, over Tailscale ssh)
  1. Launch throwaway windowed Chrome on its own profile (leaves live tabs alone):
       nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         --remote-debugging-port=9333 "--remote-allow-origins=*" \
         --user-data-dir=/tmp/scrape-profile --no-first-run --no-default-browser-check \
         --window-size=1280,900 >/tmp/scrape-chrome.log 2>&1 &
     (NB: quote --remote-allow-origins=* or zsh glob-expands it → 403 WS handshake.)
  2. venv with websocket-client:  python3 -m venv /tmp/scrape-venv &&
       /tmp/scrape-venv/bin/pip install websocket-client
  3. base64-ship this file, then:
       /tmp/scrape-venv/bin/python decathlon_extract.py <PDP-url> [<PDP-url> ...]
  4. Cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

PDP URL shape: https://www.decathlon.ca/en/p/<slug>/<productGroupID>/<variantcode>
Find candidates: web_search "site:decathlon.ca <category> <keyword>"

OUTPUT (one JSON object per URL):
  {url, name, brand, rating, review_count, image, currency,
   composition (list of "Main fabric: 38.0% Cotton, 62.0% Polyester" lines),
   natural_pct (from the Main/representative line), colors:[{color,price,availability,url,image}],
   any_in_stock}

DATA SOURCES (verified 2026-08-27):
  - JSON-LD: ProductGroup (name/brand/rating) + one Product per COLOUR
    (offers.availability, offers.priceSpecification.price CAD, image, color, url).
  - Composition: rendered outerHTML, div.specifications__block whose <h4> == "Composition",
    each <p class="specifications__item"> = one fabric line ("Main fabric: 38.0% Cotton, ...").
    Simple items with no spec block fall back to the JSON-LD description ("...100% cotton").
LIMITATION: live PER-SIZE stock is NOT in the first render (size buttons need a click).
    Per-COLOUR availability IS reliable (JSON-LD). Treat per-size as verify-on-page.
"""
import json, sys, time, re, urllib.request, websocket

CDP = "http://127.0.0.1:9333"
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "lyocell",
           "tencel", "jute", "ramie", "merino", "alpaca", "mohair")

def _new_tab(url="about:blank"):
    req = urllib.request.Request(CDP + "/json/new?" + url, method="PUT")
    return json.load(urllib.request.urlopen(req))

def _render(url, wait=13):
    t = _new_tab("about:blank")
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], max_size=None)
    i = [0]
    def cmd(m, p=None):
        i[0] += 1; mid = i[0]
        ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
        while True:
            x = json.loads(ws.recv())
            if x.get("id") == mid:
                return x
    cmd("Page.enable"); cmd("Runtime.enable")
    cmd("Page.navigate", {"url": url})
    time.sleep(wait)
    lds = cmd("Runtime.evaluate", {"expression":
        "JSON.stringify([...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s=>s.textContent))",
        "returnByValue": True})["result"]["result"]["value"]
    html = cmd("Runtime.evaluate", {"expression": "document.documentElement.outerHTML",
        "returnByValue": True})["result"]["result"]["value"]
    ws.close()
    return json.loads(lds), html

def _composition_lines(html):
    # find the specifications__block whose title is "Composition"
    lines = []
    for m in re.finditer(r'<div class="specifications__block">(.*?)</div>', html, re.S):
        block = m.group(1)
        if re.search(r'<h4[^>]*>\s*Composition\s*</h4>', block, re.I):
            for pm in re.finditer(r'<p class="specifications__item[^"]*"[^>]*>([^<]*)</p>', block):
                txt = pm.group(1).strip()
                if txt:
                    lines.append(txt)
    return lines

def _natural_pct(line):
    # line like "Main fabric: 38.0% Cotton, 62.0% Polyester" or "100% cotton"
    total_nat = 0.0
    for pm in re.finditer(r'(\d+(?:\.\d+)?)\s*%\s*([A-Za-z]+)', line):
        pct = float(pm.group(1)); fib = pm.group(2).lower()
        if any(fib.startswith(n) for n in NATURAL):
            total_nat += pct
    return round(total_nat, 1)

def extract(url):
    lds, html = _render(url)
    objs = []
    for raw in lds:
        try:
            j = json.loads(raw)
        except Exception:
            continue
        objs += j.get("@graph", [j]) if isinstance(j, dict) else j
    pg = next((o for o in objs if o.get("@type") == "ProductGroup"), None)
    prods = [o for o in objs if o.get("@type") == "Product"]
    name = (pg or (prods[0] if prods else {})).get("name")
    brand = (pg or {}).get("brand", {})
    brand = brand.get("name") if isinstance(brand, dict) else brand
    rating = (pg or {}).get("aggregateRating", {})
    colors = []
    for p in prods:
        off = p.get("offers", {})
        if isinstance(off, list):
            off = off[0] if off else {}
        price = (off.get("priceSpecification") or {}).get("price") or off.get("price")
        colors.append({
            "color": p.get("color"),
            "price": price,
            "availability": str(off.get("availability", "")).replace("https://schema.org/", ""),
            "url": off.get("url"),
            "image": p.get("image"),
        })
    comp = _composition_lines(html)
    if not comp:
        desc = (pg or (prods[0] if prods else {})).get("description", "")
        m = re.search(r'\d+\s*%\s*[A-Za-z]+', desc)
        if m:
            comp = [desc[max(0, m.start()-10):m.end()+30].strip()]
    natural_pct = _natural_pct(comp[0]) if comp else None
    return {
        "url": url,
        "name": name,
        "brand": brand,
        "rating": rating.get("ratingValue"),
        "review_count": rating.get("reviewCount"),
        "image": colors[0]["image"] if colors else None,
        "currency": "CAD",
        "composition": comp,
        "natural_pct": natural_pct,
        "colors": colors,
        "any_in_stock": any(c["availability"] == "InStock" for c in colors),
    }

if __name__ == "__main__":
    out = [extract(u) for u in sys.argv[1:]]
    print(json.dumps(out, indent=2))
