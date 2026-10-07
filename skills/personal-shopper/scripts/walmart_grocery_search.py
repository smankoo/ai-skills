#!/usr/bin/env python3
"""Run ON the iMac. Walmart.ca grocery search with homepage warm-up in ONE tab (PerimeterX).
Usage: walmart_search.py "query1" "query2" ...  -> one JSON line per query with the top tiles."""
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
  const tiles = [...document.querySelectorAll('[data-item-id], [data-testid="item-stack"] > div, div[role="group"]')];
  const out = [];
  for (const el of tiles) {
    const tx = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!/\$\s?\d/.test(tx) || tx.length > 600) continue;
    const a = el.querySelector('a[href*="/ip/"]');
    out.push({text: tx.slice(0, 260), url: a ? a.href.split('?')[0] : ''});
    if (out.length >= 8) break;
  }
  return {ready: out.length > 0, title: document.title, items: out};
})()"""
call("Page.enable")
call("Page.navigate", url="https://www.walmart.ca/en"); time.sleep(12)
for q in sys.argv[1:]:
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
