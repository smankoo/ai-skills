#!/usr/bin/env python3
"""
tommy_extract.py — Tommy Hilfiger Canada (ca.tommy.com) product extractor.

Tommy Hilfiger CA runs on Salesforce Commerce Cloud (Demandware) behind an
**Akamai** passive-fingerprint wall. From the VPS every path is walled and none
is fixable VPS-side:
  - curl / requests                        -> 403 (Server: AkamaiGHost)
  - web_extract (Crawl4AI headless)        -> "Blocked by anti-bot protection: HTTP 403"
  - the Demandware /dw/shop OCAPI endpoint  -> 403
  - .json on the PDP path                   -> 403
It is a PASSIVE wall (no press-and-hold), so an exit node does NOT help. The
reliable path is a real WINDOWED Chrome on Sumeet's Mac driven over CDP
(retail-bot-wall-bypass skill, rung 3). Verified 2026-08-17: ca.tommy.com loaded
clean over CDP with a ~13-14s render wait; no interactive challenge.

DATA SOURCES on the rendered PDP (all reliable):
  1. JSON-LD `Product` (script[type=application/ld+json]) — the money block.
     Single Product (NOT ProductGroup, so NO per-size variant array here).
     Carries: name, image (scene7 URL), offers.price (the SALE/current price),
     offers.priceCurrency, offers.availability (product-level InStock/OOS), sku.
  2. Composition — a leaf `div.content-column` whose text is the fibre line,
     e.g. "98% organic cotton, 2% elastane." / "100% regenerative cotton."
     (matched generically: a childless element with "N%" + a fibre name).
     NOT in the JSON-LD. This is the critical natural-fibre field.
  3. Original price + %off — the first `[class*=price]` element's innerText,
     e.g. "$99.50 CAD $49.75 CAD 50% off" (sale price = JSON-LD; the higher
     number is the original / compare-at).
  4. Per-size stock — `label.size-enabled` (buyable) vs `label.size-disabled`
     (OOS). Colour swatches share the container but have NO `size-*` class, so
     filter on `size-` to isolate real sizes. (Colours: grab their label text.)

HOW TO RUN (from the VPS, driving Chrome on the Mac over Tailscale):
  # 1. On the Mac, launch a throwaway debug Chrome (windowed, NOT headless):
  ssh sumeet@100.116.71.40 'export PATH=/opt/homebrew/bin:$PATH; \
    nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9333 "--remote-allow-origins=*" \
      --user-data-dir=/tmp/scrape-profile --no-first-run --no-default-browser-check \
      --window-size=1280,900 >/tmp/scrape-chrome.log 2>&1 &'
  # 2. venv with websocket-client (system pip is PEP-668 blocked):
  ssh sumeet@... 'python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client'
  # 3. base64-ship THIS file to the Mac, then:
  ssh sumeet@... '/tmp/scrape-venv/bin/python /tmp/tommy_extract.py <url> [<url> ...]'
  # 4. Cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

CRITICAL FLAGS: NO --headless (HeadlessChrome UA gets flagged); quote
"--remote-allow-origins=*" or zsh globs it -> 403 WS handshake; Chrome v151+
needs PUT (not GET) on /json/new.

Product URL shape: https://ca.tommy.com/en/<dept>/.../<slug>/<STYLE>-<COLOR>.html
e.g. .../regular-fit-gingham-oxford-shirt/78JA876-WEB.html . The <STYLE>-<COLOR>
is the SKU/style code (matches JSON-LD mpn/sku, e.g. 78JA876-WEB).
Find candidate URLs via web_search "site:ca.tommy.com <category> <keyword>".

Output shape (one dict per URL):
  {url, style, name, image, currency, price (sale), original_price, pct_off,
   availability, composition, natural_pct,
   sizes: [{size, in_stock}], colors: [str], any_size_in_stock}
"""
import json, re, sys, time, urllib.request

CDP = "http://localhost:9333"
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "jute", "ramie", "alpaca", "merino", "mohair", "cupro")
# NOTE: "organic cotton" / "regenerative cotton" still count as cotton (natural).
# Viscose/rayon/modal are semi-synthetic -> counted synthetic per the skill rule.


def open_tab(url):
    req = urllib.request.Request(CDP + "/json/new?" + url, method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def ev(ws, expr, mid):
    ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mid:
            return m.get("result", {}).get("result", {}).get("value")


JS = r"""
(() => {
  const out = {};
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch(e) { return null; } })
    .filter(Boolean);
  const p = lds.find(j => j['@type'] === 'Product');
  if (p) {
    out.name = p.name;
    out.sku = p.sku || p.mpn;
    out.image = Array.isArray(p.image) ? p.image[0] : p.image;
    const o = Array.isArray(p.offers) ? p.offers[0] : (p.offers || {});
    out.price = o.price;
    out.currency = o.priceCurrency;
    out.availability = String(o.availability || '').replace(/https?:\/\/schema\.org\//, '');
  }
  // Composition: a childless element with "N%" + a fibre name.
  const fibre = /cotton|polyester|elastane|wool|linen|viscose|nylon|silk|cashmere|lyocell|tencel|spandex|acrylic|rayon|modal|hemp|cupro/i;
  const cands = [...document.querySelectorAll('div.content-column, *')]
    .filter(e => e.children.length === 0 && /\d{1,3}\s*%/.test(e.textContent) && fibre.test(e.textContent))
    .map(e => e.textContent.trim()).filter(t => t.length < 120);
  out.composition = [...new Set(cands)][0] || null;
  // Original price + %off from the first price container's text.
  const pe = document.querySelector('[class*=price i]');
  out.priceText = pe ? pe.innerText.replace(/\s+/g, ' ').trim().slice(0, 80) : null;
  // Per-size stock: label.size-enabled / label.size-disabled (colours lack size-*).
  out.sizes = [...document.querySelectorAll('label[class*=size-]')]
    .map(l => ({ size: (l.getAttribute('aria-label') || l.textContent).trim().slice(0, 12),
                 in_stock: /size-enabled/.test(l.className) }))
    .filter(s => s.size && s.size.length <= 8);
  // Colours: swatch labels without a size- class, from the colour swatch group.
  out.colors = [...document.querySelectorAll('[class*=swatch i] label, [class*=color i] label')]
    .map(l => (l.getAttribute('aria-label') || l.textContent).trim())
    .filter(t => t && !/^(XXS|XS|S|M|L|XL|XXL|XXXL|\d+)$/i.test(t) && t.length < 30);
  out.colors = [...new Set(out.colors)].slice(0, 12);
  return out;
})()
"""


def natural_pct(comp):
    if not comp:
        return None
    parts = re.findall(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z ]*)", comp)
    if not parts:
        if any(f in comp.lower() for f in NATURAL) and "%" not in comp:
            return 100
        return None
    total = sum(int(p) for p, _ in parts)
    nat = sum(int(p) for p, f in parts if any(n in f.lower() for n in NATURAL))
    return round(nat * 100 / total) if total else None


def parse_prices(sale, price_text):
    """sale = JSON-LD current price; price_text may hold the original + %off."""
    original, pct = None, None
    if price_text:
        # ONLY $-prefixed amounts — otherwise a "40% off" tail is read as a price.
        nums = [float(x) for x in re.findall(r"\$\s?(\d+(?:\.\d\d)?)", price_text)]
        if nums:
            hi = max(nums)
            try:
                if sale and hi > float(sale) + 0.001:
                    original = hi
            except (TypeError, ValueError):
                pass
        m = re.search(r"(\d{1,2})\s*%\s*off", price_text, re.I)
        if m:
            pct = int(m.group(1))
    return original, pct


def extract(url):
    import websocket  # lazy: only the live CDP path needs it, not the pure parsers
    tab = open_tab("about:blank")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    for i, m in enumerate([("Page.enable", {}), ("Runtime.enable", {}),
                           ("Page.navigate", {"url": url})], 1):
        ws.send(json.dumps({"id": i, "method": m[0], "params": m[1]}))
    time.sleep(14)  # render + passive Akamai challenge auto-clear
    v = ev(ws, JS, 100) or {}
    ws.close()
    comp = v.get("composition")
    original, pct = parse_prices(v.get("price"), v.get("priceText"))
    style_m = re.search(r"/([0-9A-Z]+-[0-9A-Z]+)\.html", url)
    return {
        "url": url,
        "style": v.get("sku") or (style_m.group(1) if style_m else None),
        "name": v.get("name"),
        "image": v.get("image"),
        "currency": v.get("currency"),
        "price": v.get("price"),
        "original_price": original,
        "pct_off": pct,
        "availability": v.get("availability"),
        "composition": comp,
        "natural_pct": natural_pct(comp),
        "sizes": v.get("sizes") or [],
        "colors": v.get("colors") or [],
        "any_size_in_stock": any(s.get("in_stock") for s in (v.get("sizes") or [])),
    }


if __name__ == "__main__":
    print(json.dumps([extract(u) for u in sys.argv[1:]], indent=2))
