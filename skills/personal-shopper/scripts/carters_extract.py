#!/usr/bin/env python3
"""
carters_extract.py — Carter's / OshKosh Canada (cartersoshkosh.ca) product extractor.

Carter's CA (and US carters.com / oshkosh.com — same Salesforce Commerce Cloud
platform) sits behind Cloudflare + PerimeterX. From the VPS every path is walled:
  - curl / requests            -> 403 "Just a moment..." (Cloudflare)
  - web_extract (Crawl4AI)     -> "Blocked by anti-bot protection: PerimeterX block"
It is a PASSIVE fingerprint wall, so an exit node does NOT help. The reliable path
is a real WINDOWED Chrome on Sumeet's Mac driven over CDP (retail-bot-wall-bypass
skill, rung 3). Verified 2026-08-15.

DATA SOURCES on the rendered PDP:
  1. JSON-LD `ProductGroup` (script[type=application/ld+json]) — the money block.
     Carries per-size variants: hasVariant[].{size, sku, offers.price,
     offers.priceCurrency, offers.availability}. This gives PER-SIZE STOCK + PRICE
     cleanly (no accordion clicking, no --unavailable class hunting).
  2. Product description block `[class*=description i]` — carries the
     "Fabric & Care:" section with the fibre COMPOSITION (e.g. "100% cotton"),
     "Imported", and OEKO-TEX cert. This is the critical natural-fibre field; it is
     NOT in the JSON-LD.
  3. og:image / JSON-LD image — Demandware static image URL.

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
  ssh sumeet@... '/tmp/scrape-venv/bin/python /tmp/carters_extract.py <url> [<url> ...]'
  # 4. Cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

CRITICAL FLAGS: NO --headless (HeadlessChrome UA gets flagged); quote
"--remote-allow-origins=*" or zsh globs it -> 403 WS handshake; Chrome v151+ needs
PUT (not GET) on /json/new.

Product URL shape: https://www.cartersoshkosh.ca/en_CA/<slug>/V_<styleid>.html
Style id V_<8 digits> is the productGroupID in the JSON-LD.

Output shape (one dict per URL):
  {url, name, brand, image, currency, composition, natural_pct,
   sizes: [{size, sku, price, availability}], any_in_stock}
"""
import json, re, sys, time, urllib.request, websocket

CDP = "http://localhost:9333"
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "jute", "ramie", "alpaca", "merino", "mohair")

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
  let pg = lds.find(j => j['@type'] === 'ProductGroup')
        || lds.find(j => j['@type'] === 'Product');
  if (pg) {
    out.name = pg.name;
    out.brand = pg.brand && (pg.brand.name || pg.brand);
    out.image = Array.isArray(pg.image) ? pg.image[0] : pg.image;
    const vars = pg.hasVariant || (pg.offers ? [pg] : []);
    out.sizes = (vars || []).map(v => {
      const o = Array.isArray(v.offers) ? v.offers[0] : (v.offers || {});
      return { size: v.size || '', sku: v.sku || '',
               price: o.price, currency: o.priceCurrency,
               availability: String(o.availability || '').replace('https://schema.org/', '') };
    });
  }
  const og = document.querySelector('meta[property="og:image"]');
  if (og && !out.image) out.image = og.content;
  // Fabric & Care block from the description container
  const d = document.querySelector('[class*=description i]');
  if (d) out.desc = d.innerText.trim();
  return out;
})()
"""

def parse_composition(desc):
    """Return the fibre-composition line from the 'Fabric & Care:' section."""
    if not desc:
        return None
    m = re.search(r"Fabric\s*&?\s*Care:?\s*\n+([^\n]+)", desc, re.I)
    if m and re.search(r"\d{1,3}\s*%|\bcotton\b|\bpolyester\b", m.group(1), re.I):
        return m.group(1).strip()
    # fallback: first "N% fibre" line anywhere in desc
    m = re.search(r"\d{1,3}\s*%\s*[A-Za-z][A-Za-z /]{2,40}", desc)
    return m.group(0).strip() if m else None

def natural_pct(comp):
    if not comp:
        return None
    parts = re.findall(r"(\d{1,3})\s*%\s*([A-Za-z]+)", comp)
    if not parts:
        # "100% cotton" with no explicit split, or bare fibre name
        if any(f in comp.lower() for f in NATURAL) and "%" not in comp:
            return 100
        return None
    total = sum(int(p) for p, _ in parts)
    nat = sum(int(p) for p, f in parts if f.lower() in NATURAL)
    return round(nat * 100 / total) if total else None

def extract(url):
    tab = open_tab("about:blank")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
    ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
    ws.send(json.dumps({"id": 3, "method": "Page.navigate", "params": {"url": url}}))
    time.sleep(13)  # render + passive challenge auto-clear
    v = ev(ws, JS, 100) or {}
    ws.close()
    comp = parse_composition(v.get("desc"))
    sizes = v.get("sizes") or []
    return {
        "url": url,
        "name": v.get("name"),
        "brand": v.get("brand"),
        "image": v.get("image"),
        "currency": (sizes[0].get("currency") if sizes else None),
        "composition": comp,
        "natural_pct": natural_pct(comp),
        "sizes": [{"size": s["size"], "sku": s["sku"], "price": s["price"],
                   "availability": s["availability"]} for s in sizes],
        "any_in_stock": any(s.get("availability") == "InStock" for s in sizes),
    }

if __name__ == "__main__":
    print(json.dumps([extract(u) for u in sys.argv[1:]], indent=2))
