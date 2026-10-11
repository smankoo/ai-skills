#!/usr/bin/env python3
"""Run ON the iMac. Walmart.ca grocery search with homepage warm-up in ONE tab (PerimeterX).
Usage: walmart_grocery_search.py [--ads] "query1" "query2" ...  -> one JSON line per query with the top tiles
  (price, unit_price, was, rollback, oos, text, /ip/ url). Sponsored tiles are skipped unless --ads.
Run: scp it to the iMac ~/.hermes/, then  cd ~/.hermes && costco-venv/bin/python walmart_grocery_search.py "2% milk 4L"
Validated + fixed 2026-10-08 (dedupe, skip ads, real /ip/ URLs, parsed price fields)."""
import json, sys, time, urllib.request, urllib.parse
import websocket
CDP = "http://127.0.0.1:9334"
t = json.loads(urllib.request.urlopen(urllib.request.Request(CDP + "/json/new?about:blank", method="PUT"), timeout=10).read())
ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
n = [0]
def call(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]: return r
def ev(expr):
    r = call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
    return r.get("result", {}).get("result", {}).get("value")
EXTRACT = r"""(() => {
  const t = document.body ? document.body.innerText : '';
  if (/Verify Your Identity|blocked/i.test(location.href + document.title)) return {blocked: location.href};
  // 2026-10-08 fix: one tile per [data-item-id] (nested selectors double-counted), skip Sponsored,
  // take the real /ip/ link (sponsored tiles' first <a> is a /wapcrs/track redirect).
  const tiles = [...document.querySelectorAll('[data-item-id]')];
  const out = [], seen = new Set(); let ads = 0;
  for (const el of tiles) {
    const id = el.getAttribute('data-item-id'); if (seen.has(id)) continue; seen.add(id);
    const tx = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!/\$\s?\d|\d+\u00a2/.test(tx) || tx.length > 800) continue;
    if (/\bSponsored\b/.test(tx) && !KEEP_ADS) { ads++; continue; }
    const a = [...el.querySelectorAll('a[href]')].map(x => x.href).find(h => /\/ip\//.test(h)) || '';
    const cur = (tx.match(/current price (?:Now )?\$?(\d[\d,]*(?:\.\d\d)?\u00a2?)/) || [])[1] || null;
    const unit = (tx.match(/(\$?[\d.]+\u00a2?\/(?:100g|100ml|1kg|kg|lb|ea|1l|l|100 g|100 ml))/i) || [])[1] || null;
    const was = (tx.match(/Was \$?([\d.,]+)/) || [])[1] || null;
    out.push({price: cur, unit_price: unit, was: was, rollback: /Rollback/i.test(tx),
              oos: /Out of stock/i.test(tx), text: tx.slice(0, 220), url: a.split('?')[0]});
    if (out.length >= 8) break;
  }
  return {ready: out.length > 0, title: document.title, ads_skipped: ads, items: out};
})()""".replace("KEEP_ADS", "true" if "--ads" in sys.argv else "false")
call("Page.enable")
call("Page.navigate", url="https://www.walmart.ca/en"); time.sleep(12)
for q in [x for x in sys.argv[1:] if x != "--ads"]:
    url = "https://www.walmart.ca/en/search?q=" + urllib.parse.quote(q)
    ev(f"location.assign({json.dumps(url)})")
    res = None
    for _ in range(10):
        time.sleep(2.5)
        res = ev(EXTRACT)
        if res and (res.get("ready") or res.get("blocked")): break
    print(json.dumps({"q": q, "data": res})); sys.stdout.flush()
    time.sleep(4)
ws.close()
urllib.request.urlopen(CDP + "/json/close/" + t["id"], timeout=10)
