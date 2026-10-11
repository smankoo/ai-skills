#!/usr/bin/env python3
"""
zara_extract.py — Zara CA product extractor.

Zara hard-403s the VPS on EVERY transport (curl, web_extract, its own JSON API)
via an Akamai passive-fingerprint wall — same class as Tommy Hilfiger. There is
NO VPS-side fix (an exit node changes the IP, not the fingerprint). So this runs
over CDP against a real windowed Chrome on the Mac (see retail-bot-wall-bypass):

    # On the Mac (over ssh sumeet@100.116.71.40, PATH=/opt/homebrew/bin:...):
    nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9333 "--remote-allow-origins=*" \
      --user-data-dir=/tmp/scrape-profile --no-first-run --no-default-browser-check \
      --window-size=1280,900 >/tmp/scrape-chrome.log 2>&1 &
    python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client
    /tmp/scrape-venv/bin/python zara_extract.py <PDP-URL> [<PDP-URL> ...]
    # cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

Why CDP + not curl-the-API: Zara's public JSON API also 403s from the VPS, and
its endpoints key off the INTERNAL numeric productId (e.g. 545944283), not the
SEO id in the URL (p01997303). But every Zara PDP embeds a full JSON-LD
`ProductGroup` block that already carries everything the skill needs — name,
brand, material/composition, images, and one `hasVariant` per size×colour with
`offers.price` + `offers.availability` (InStock/OutOfStock). So we just render
the PDP once (Akamai clears in ~13s), parse the JSON-LD, done. No API call, no
accordion click, no DOM stock-hunt.

Output shape per URL:
  {url, name, brand, composition, natural_pct, material, images:[...],
   colors:[...], sizes:[{size,color,price,currency,in_stock}], any_in_stock}
"""
import json, time, urllib.request, sys, re
for p in ("/tmp/scrape-venv/lib/python3.14/site-packages",
          "/tmp/scrape-venv/lib/python3.13/site-packages",
          "/tmp/scrape-venv/lib/python3.12/site-packages"):
    sys.path.insert(0, p)
import websocket

CDP = "http://127.0.0.1:9333"
SYNTH = re.compile(r"polyester|nylon|acrylic|elastane|spandex|viscose|rayon|modal|polyamide|acetate", re.I)
NAT = re.compile(r"cotton|wool|linen|silk|cashmere|lyocell|tencel|hemp|ramie|merino|mohair|alpaca", re.I)

def natural_pct(comp):
    """Sum natural-fibre % from a composition string like '80% cotton, 20% polyester'."""
    if not comp:
        return None
    tot = 0
    for m in re.finditer(r"(\d{1,3})\s*%\s*([A-Za-z ]+)", comp):
        pct, fibre = int(m.group(1)), m.group(2)
        if NAT.search(fibre) and not SYNTH.search(fibre):
            tot += pct
    return tot or None

def new_tab():
    req = urllib.request.Request(CDP + "/json/new?about:blank", method="PUT")
    return json.load(urllib.request.urlopen(req))

def extract(ws, send, ev, url):
    send("Page.navigate", {"url": url})
    time.sleep(13)
    ld = ev(r"""(() => {
      for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
        try { const j = JSON.parse(s.textContent);
          if (j['@type']==='ProductGroup' || j['@type']==='Product') return s.textContent;
        } catch(e){}
      }
      return null;
    })()""", ap=False)
    if not ld:
        return {"url": url, "error": "no JSON-LD"}
    j = json.loads(ld)
    # composition: prefer OUTER SHELL additionalProperty, else material
    comp = None
    for ap in (j.get("additionalProperty") or []):
        if str(ap.get("propertyID", "")).lower() == "composition":
            comp = ap.get("value"); break
    comp = comp or j.get("material")
    imgs = j.get("image", [])
    if isinstance(imgs, str): imgs = [imgs]
    sizes, colors = [], set()
    for v in j.get("hasVariant", []):
        o = v.get("offers") or {}
        if isinstance(o, list): o = o[0] if o else {}
        colors.add(v.get("color"))
        sizes.append({"size": v.get("size"), "color": v.get("color"),
                      "price": o.get("price"), "currency": o.get("priceCurrency"),
                      "in_stock": str(o.get("availability", "")).rsplit("/", 1)[-1] == "InStock"})
    return {
        "url": url, "name": j.get("name"),
        "brand": (j.get("brand") or {}).get("name") if isinstance(j.get("brand"), dict) else j.get("brand"),
        "composition": comp, "natural_pct": natural_pct(comp), "material": j.get("material"),
        "images": imgs[:4], "colors": sorted(c for c in colors if c),
        "sizes": sizes, "any_in_stock": any(s["in_stock"] for s in sizes),
    }

def main():
    urls = sys.argv[1:]
    if not urls:
        print("usage: zara_extract.py <PDP-URL> ..."); sys.exit(1)
    tab = new_tab()
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], max_size=None)
    _id = [0]
    def send(m, p=None):
        _id[0] += 1
        ws.send(json.dumps({"id": _id[0], "method": m, "params": p or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == _id[0]: return r
    def ev(e, ap=True):
        r = send("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": ap})
        return r.get("result", {}).get("result", {}).get("value")
    send("Page.enable"); send("Runtime.enable")
    # warm-up navigation to clear Akamai / set cookies once
    send("Page.navigate", {"url": "https://www.zara.com/ca/en/"}); time.sleep(10)
    out = [extract(ws, send, ev, u) for u in urls]
    ws.close()
    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
