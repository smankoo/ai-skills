#!/usr/bin/env python3
"""canadiantire_extract.py — Canadian Tire (canadiantire.ca, CT/FGL "Nucleus" stack) extractor.

Same platform + same wall as Mark's / Sport Chek: VPS is hard-Akamai-403 on curl AND on the
product API (apim.canadiantire.ca and the same-origin /api/v1/product/... both 403 the VPS even
with the leaked subscription-key). web_extract renders only the page shell — the PDP is an SPA
that hydrates from XHR. => CDP windowed Chrome on the Mac + NETWORK-INTERCEPT the app's own XHRs
(do NOT replay them with fetch(): same 401/400 behaviour as Mark's).

The two money XHRs the PDP fires (same-origin, www.canadiantire.ca — verified 2026-09-09):
  1. GET /api/v1/product/api/v2/product/productFamily/<id>?baseStoreId=CTR&lang=en_CA&storeId=<n>&light=true
       -> name, brand.label, images[].url, skus[] with specifications[] + optionIds[]
  2. GET /api/v1/product/api/v2/product/sku/PriceAvailability?lang=en_CA&storeId=<n>&cache=true&pCode=<id>&isLoyaltyUser=false
       -> skus[]: currentPrice.value, originalPrice.value, isOnSale,
          fulfillment.availability.Corporate.Quantity (DC stock) + quantity (store stock)
Join on sku `code`. <id> = tail of the PDP URL: .../<slug>-1422111p.html (ends in 'p', not
Mark's 'f'). Bonus (not needed): content.syndigo.com/page/<uuid>/<id>.json = rich marketing copy.

HOW TO RUN (on the Mac, per retail-bot-wall-bypass rung 3):
  # 1. launch windowed debug Chrome on :9333 with a throwaway profile (see that skill)
  # 2. python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client
  # 3. base64-ship this file, then:
  /tmp/scrape-venv/bin/python3 canadiantire_extract.py \
      "https://www.canadiantire.ca/en/pdp/<slug>-<id>p.html" ...
  # cleanup: pkill -f 'remote-debugging-port=9333'; rm -rf /tmp/scrape-profile /tmp/scrape-venv

Output per URL (JSON array on stdout):
  {url, id, name, brand, image, composition, natural_pct, currency, price, price_max, on_sale,
   variants:[{sku, size, colour, price, original_price, on_sale, qty, in_stock, urgent_low}],
   any_in_stock}
Composition is usually empty (general merch, not apparel); fabric specs parse when present.
"""
import json, re, sys, time, urllib.request
import websocket

CDP = "http://127.0.0.1:9333"
NATURAL = {"cotton","wool","linen","silk","cashmere","lyocell","tencel","hemp","merino",
           "ramie","jute","mohair","alpaca","angora"}

def spec(specs, code):
    for s in (specs or []):
        if s.get("code")==code:
            return (s.get("value") or "").strip()
    return ""

def build_composition(specs):
    parts=[]
    for n in (1,2,3):
        fab = spec(specs, f"primary_fabric_{n}_cd")
        pct = spec(specs, f"primary_fabric_{n}_percentage_amt")
        if fab and pct:
            parts.append((fab, pct))
    if not parts:
        return "", None
    txt = ", ".join(f"{p}% {f}" for f,p in parts)
    nat=0.0
    for f,p in parts:
        try: v=float(p)
        except ValueError: v=0
        if f.lower() in NATURAL: nat+=v
    return txt, round(nat,1)

def opt(optids, prefix):
    for o in (optids or []):
        if o.startswith(prefix):
            return o[len(prefix):]
    return ""

def parse(d):
    fam = d.get("family") or {}
    pa  = d.get("price") or {}
    imgs = fam.get("images") or []
    fskus = fam.get("skus") or []
    comp, nat = "", None
    for s in fskus:
        c,n = build_composition(s.get("specifications"))
        if c: comp, nat = c, n; break
    pmap = {p.get("code"): p for p in (pa.get("skus") or [])}
    variants=[]; prices=[]
    for s in fskus:
        code=s.get("code"); p=pmap.get(code, {})
        cur=(p.get("currentPrice") or {}).get("value")
        orig=(p.get("originalPrice") or {}).get("value")
        avail=(p.get("fulfillment") or {}).get("availability") or {}
        qty=((avail.get("Corporate") or {}).get("Quantity")) or ((avail.get("quantity")) if isinstance(avail.get("quantity"),(int,float)) else None)
        variants.append({
            "sku": code,
            "size": opt(s.get("optionIds"), "SIZE_CD_"),
            "colour": opt(s.get("optionIds"), "COLOUR_") or spec(s.get("specifications"),"colour_group_cd"),
            "price": cur, "original_price": orig,
            "on_sale": bool(p.get("isOnSale")),
            "qty": qty, "in_stock": (qty or 0) > 0,
            "urgent_low": bool(p.get("isUrgentLowStock")),
        })
        if cur: prices.append(cur)
    return {
        "url": d.get("url"), "id": d.get("id"),
        "name": fam.get("name"), "brand": (fam.get("brand") or {}).get("label"),
        "image": imgs[0]["url"] if imgs else None,
        "composition": comp, "natural_pct": nat,
        "currency": "CAD",
        "price": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "on_sale": any(v["on_sale"] for v in variants),
        "variants": variants,
        "any_in_stock": any(v["in_stock"] for v in variants),
    }

def run(url, wait=18):
    req = urllib.request.Request(f"{CDP}/json/new?about:blank", method="PUT")
    tab = json.load(urllib.request.urlopen(req, timeout=15))
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=40)
    mid=[0]
    def send(method, params=None):
        mid[0]+=1
        ws.send(json.dumps({"id":mid[0],"method":method,"params":params or {}}))
        return mid[0]
    send("Network.enable"); send("Page.enable")
    time.sleep(0.4)
    send("Page.navigate", {"url": url})
    hits=[]
    deadline=time.time()+wait
    while time.time()<deadline:
        try:
            ws.settimeout(2); m=json.loads(ws.recv())
        except Exception:
            continue
        if m.get("method")=="Network.responseReceived":
            u=m["params"]["response"]["url"]
            if "/product/productFamily/" in u and "List" not in u:
                hits.append(("family", m["params"]["requestId"]))
            elif "PriceAvailability" in u:
                hits.append(("price", m["params"]["requestId"]))
    combined={"url":url}
    for kind, rid in hits:
        bid=send("Network.getResponseBody", {"requestId": rid})
        body=None; t0=time.time()
        while time.time()-t0<6:
            try: mm=json.loads(ws.recv())
            except Exception: break
            if mm.get("id")==bid:
                body=mm.get("result",{}).get("body"); break
        if body:
            try:
                j=json.loads(body)
                combined["family" if kind=="family" else "price"]=j
            except Exception:
                pass
    ws.close()
    m=re.search(r"-([0-9]+p)\.html", url, re.I)
    combined["id"]=m.group(1) if m else None
    return parse(combined)

if __name__=="__main__":
    urls=sys.argv[1:] or [
        "https://www.canadiantire.ca/en/pdp/thermos-stainless-steel-water-bottle-with-vacuum-insulation-assorted-colours-354-ml-1422111p.html",
        "https://www.canadiantire.ca/en/pdp/noma-outdoor-warm-white-led-battery-operated-string-lights-20-ft-0528033p.html",
    ]
    print(json.dumps([run(u) for u in urls], indent=2))
