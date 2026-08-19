#!/usr/bin/env python3
"""
sportchek_extract.py — Sport Chek (sportchek.ca) product extractor.

Sport Chek runs on the Canadian Tire / FGL "Nucleus" stack. From the VPS EVERY
transport is Akamai-walled (curl/web_extract/APIM gateway all hard-403 "Access
Denied"), and it is a passive fingerprint wall (no interactive press-and-hold),
so an exit node does NOT help. Run this over CDP windowed Chrome on the Mac —
rung 3 of retail-bot-wall-bypass. The page renders clean in ~14s, no challenge.

HOW TO RUN (on Sumeet's Mac, ssh sumeet@100.116.71.40):
  # 1. launch windowed debug Chrome on a throwaway profile (NOT --headless):
  nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9333 "--remote-allow-origins=*" \
    --user-data-dir=/tmp/scrape-profile --no-first-run --no-default-browser-check \
    --window-size=1280,900 >/tmp/scrape-chrome.log 2>&1 &
  # 2. venv with websocket-client (system pip is PEP-668 blocked):
  python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client
  # 3. run:
  /tmp/scrape-venv/bin/python sportchek_extract.py <PDP-url> [<PDP-url> ...]
  # 4. cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

Output per URL (JSON array on stdout):
  {url, name, brand, image, price, was_price, on_sale, final_sale, currency,
   composition, natural_pct, sizes:[{size, in_stock}], description, item_id}

PDP URL shape: https://www.sportchek.ca/en/pdp/<slug>-<9digit>f.html
Find candidates via web_search 'site:sportchek.ca <brand> <keyword>'.
"""
import json, re, time, sys, urllib.request, websocket

CDP = "http://127.0.0.1:9333"
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "merino", "lambswool", "mohair", "alpaca", "jute", "ramie")
# viscose/rayon/modal are semi-synthetic -> counted synthetic per skill rule.

PAGE_JS = r"""
(() => {
  const out = {};
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch(e){ return null; } }).filter(Boolean);
  const flat = [];
  lds.forEach(j => { if (Array.isArray(j)) flat.push(...j); else flat.push(j); if (j['@graph']) flat.push(...j['@graph']); });
  const isProd = j => j['@type']==='Product' || (Array.isArray(j['@type']) && j['@type'].includes('Product'));
  const p = flat.find(isProd) || {};
  out.name = p.name || (document.querySelector('h1')||{}).textContent || '';
  out.brand = (p.brand && (p.brand.name || p.brand)) || '';
  out.image = Array.isArray(p.image) ? p.image[0] : (p.image || (document.querySelector('meta[property="og:image"]')||{}).content || '');
  out.description = (p.description || '').trim();
  // Price: the .nl-price__container leaf carries the full "NOW$X WAS$Y Final Sale" string.
  const container = document.querySelector('.nl-price__container');
  out.priceText = container ? (container.textContent||'').trim() : '';
  out.priceTotal = (document.querySelector('.nl-price--total, .nl-price--total--red')||{}).textContent || '';
  out.wasText = (document.querySelector('.nl-price--was')||{}).textContent || '';
  out.saleRed = !!document.querySelector('.nl-price--total--red');
  // Composition: dedicated "Contents:/Composition/Fabrication" leaf, else fall back to description prose.
  let comp = '';
  const leaves = [...document.querySelectorAll('*')].filter(el => el.children.length===0);
  for (const el of leaves) {
    const t = (el.textContent||'').trim();
    if (/^(Contents|Composition|Fabrication|Material)\s*[:\-]/i.test(t) && t.length < 200) { comp = t; break; }
  }
  out.contents = comp;
  // Sizes: .nl-variants__variant divs that are NOT colour swatches. OOS = disabled/unavailable/soldout class modifier.
  out.sizes = [...document.querySelectorAll('.nl-variants__variant')]
    .filter(el => !/colour-swatch/i.test(el.className))
    .map(el => ({ size: (el.textContent||'').trim(),
                  oos: /--(disabled|unavailable|soldout|out-of-stock)/i.test(el.className)
                       || el.getAttribute('aria-disabled')==='true' || el.disabled === true }))
    .filter(s => s.size && s.size.length < 12 && !/^(Regular|Tall|Short)$/i.test(s.size));
  return JSON.stringify(out);
})()
"""

def natural_pct(text):
    if not text:
        return None
    pairs = re.findall(r'(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /-]*)', text)
    if not pairs:
        # bare "made of 100% cotton" style — reuse same regex; if still none, unknown
        return None
    nat = 0; total = 0
    for pct, fib in pairs:
        pct = int(pct); total += pct
        if any(n in fib.lower() for n in NATURAL):
            nat += pct
    if total == 0:
        return None
    return round(nat * 100 / total)

def parse_price(d):
    txt = d.get("priceText") or d.get("priceTotal") or ""
    now = None; was = None; final_sale = "Final Sale" in txt
    m = re.search(r'NOW\s*\$?([\d,]+\.\d\d)', txt)
    if m: now = float(m.group(1).replace(',', ''))
    if now is None:
        m = re.search(r'\$?([\d,]+\.\d\d)', d.get("priceTotal") or txt)
        if m: now = float(m.group(1).replace(',', ''))
    mw = re.search(r'WAS[^$]*\$?([\d,]+\.\d\d)', txt) or re.search(r'\$?([\d,]+\.\d\d)', d.get("wasText") or "")
    if mw: was = float(mw.group(1).replace(',', ''))
    on_sale = bool(d.get("saleRed")) or (was is not None and now is not None and was > now)
    return now, was, on_sale, final_sale

def cdp(url):
    req = urllib.request.Request(CDP + "/json/new?about:blank", method="PUT")
    tab = json.load(urllib.request.urlopen(req))
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], max_size=None)
    _id = [0]
    def cmd(m, p=None):
        _id[0] += 1
        ws.send(json.dumps({"id": _id[0], "method": m, "params": p or {}}))
        while True:
            x = json.loads(ws.recv())
            if x.get("id") == _id[0]:
                return x
    cmd("Page.enable"); cmd("Runtime.enable")
    cmd("Page.navigate", {"url": url}); time.sleep(14)
    r = cmd("Runtime.evaluate", {"expression": PAGE_JS, "returnByValue": True})
    ws.close()
    return json.loads(r["result"]["result"]["value"])

def extract(url):
    d = cdp(url)
    now, was, on_sale, final_sale = parse_price(d)
    comp = d.get("contents") or ""
    comp_src = comp
    if not comp:
        # fall back to fibre% found anywhere in the description prose
        m = re.search(r'((?:\d{1,3}\s*%\s*[A-Za-z][A-Za-z /-]*[,/ ]*)+)', d.get("description", ""))
        if m: comp_src = m.group(1).strip()
    mid = re.search(r'-(\d{6,})f?\.html', url)
    return {
        "url": url, "name": d.get("name", ""), "brand": d.get("brand", ""),
        "image": d.get("image", ""), "price": now, "was_price": was,
        "on_sale": on_sale, "final_sale": final_sale, "currency": "CAD",
        "composition": comp_src, "natural_pct": natural_pct(comp_src),
        "sizes": [{"size": s["size"], "in_stock": (None if False else not s["oos"])} for s in d.get("sizes", [])],
        "description": d.get("description", "")[:300],
        "item_id": mid.group(1) if mid else None,
    }

if __name__ == "__main__":
    print(json.dumps([extract(u) for u in sys.argv[1:]], indent=2))
