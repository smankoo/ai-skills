#!/usr/bin/env python3
"""marks_extract.py — Mark's (marks.com, Canadian Tire/FGL stack) product extractor.

VPS is hard-403 walled (Akamai, edgesuite.net) on curl / .js / the product API — same
wall as Sport Chek. web_extract only renders footer chrome (SPA hydrates via XHR).
=> Drive a real WINDOWED Chrome on the Mac over CDP (see retail-bot-wall-bypass), navigate
   the PDP, then run two SAME-ORIGIN fetches from the page context. Same-origin XHR carries
   the APIM auth automatically (cookies/edge), so NO subscription-key param is needed.

Two endpoints (both same-origin, after the PDP has loaded):
  1. /api/v1/product/api/v2/product/productFamily/<id>?baseStoreId=MKS&lang=en_CA&storeId=392
       -> name, brand, images[], skus[] each with:
          specifications[] : primary_fabric_1_cd/_percentage_amt (+ _2_, _3_) = COMPOSITION,
                             fit_cd, neckline_style_cd, colour_group_cd, gender_cd, ...
          optionIds[]      : SIZE_CD_*, SECOND_SIZE_RANGE_CD_*, COLOUR_* (the size/colour of that sku)
  2. /api/v1/product/api/v2/product/sku/PriceAvailability?lang=en_CA&storeId=392&cache=true&pCode=<id>&isLoyaltyUser=false
       -> skus[] each: currentPrice.value, originalPrice.value, isOnSale, saleCut,
          isUrgentLowStock, fulfillment.availability.Corporate.Quantity (live corp stock)

Join the two on sku `code`. Composition is per-sku but identical across sizes of a colourway.
<id> = the 8-9 char style id ending in 'f', tail of the PDP URL: .../<slug>-12597467f.html

HOW TO RUN (on the Mac, after launching the CDP debug Chrome per retail-bot-wall-bypass):
  # 1. launch windowed debug chrome on :9333 with a throwaway profile (see recipe)
  # 2. python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client
  # 3. base64-ship this file to the Mac, then:
  /tmp/scrape-venv/bin/python3 marks_extract.py \
      "https://www.marks.com/en/pdp/<slug>-<id>f.html" ...
  # cleanup: pkill -f 'remote-debugging-port=9333'; rm -rf /tmp/scrape-profile /tmp/scrape-venv

Output shape per URL (JSON array on stdout):
  {url, id, name, brand, image, composition, natural_pct,
   currency, price, original_price, on_sale,
   variants:[{sku, size, second_range, colour, price, on_sale, qty, in_stock, urgent_low}],
   any_in_stock}

Verified 2026-08-26 on two live PDPs (12597467f, 71223583f): both 100% Cotton / natural_pct 100,
$19.99, per-size live stock quantities matched the PriceAvailability payload.
"""
import json, sys, time, urllib.request
CDP = "http://127.0.0.1:9333"
import websocket

NATURAL = {"cotton","wool","linen","silk","cashmere","lyocell","tencel","hemp","merino",
           "ramie","jute","mohair","alpaca","angora"}

def newtab(url):
    req = urllib.request.Request(f"{CDP}/json/new?{url}", method="PUT")
    return json.load(urllib.request.urlopen(req, timeout=15))

def evaljs(ws, expr, i=[0]):
    i[0]+=1; mid=i[0]
    ws.send(json.dumps({"id":mid,"method":"Runtime.evaluate",
        "params":{"expression":expr,"returnByValue":True,"awaitPromise":True}}))
    while True:
        m=json.loads(ws.recv())
        if m.get("id")==mid:
            return m["result"]["result"].get("value")

# runs in page context: fetch both endpoints same-origin, return raw JSON
SUBKEY = "c01ef3612328420c9f5cd9277e815a0e"  # APIM key, lifted from the PDP image URL's subscription-key= param
FETCH = r"""
(async function(){
  const m = location.pathname.match(/-([0-9]+f)\.html$/i);
  const id = m ? m[1] : null;
  const K = "%s";
  const H = {accept:'application/json', 'Ocp-Apim-Subscription-Key': K, 'subscription-key': K, 'bannerId':'MKS'};
  const out = {id, url: location.href};
  try {
    const r1 = await fetch(`/api/v1/product/api/v2/product/productFamily/${id}?baseStoreId=MKS&lang=en_CA&storeId=392&subscription-key=${K}`,{headers:H});
    out.familyStatus = r1.status; out.family = await r1.json();
  } catch(e){ out.familyErr = String(e).slice(0,150); }
  try {
    const r2 = await fetch(`/api/v1/product/api/v2/product/sku/PriceAvailability?lang=en_CA&storeId=392&cache=true&pCode=${id}&isLoyaltyUser=false&subscription-key=${K}`,{headers:H});
    out.priceStatus = r2.status; out.price = await r2.json();
  } catch(e){ out.priceErr = String(e).slice(0,150); }
  return JSON.stringify(out);
})()
""" % SUBKEY

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
        except: v=0
        if f.lower() in NATURAL: nat+=v
    return txt, round(nat,1)

def opt(optids, prefix):
    for o in (optids or []):
        if o.startswith(prefix):
            return o[len(prefix):]
    return ""

def parse(raw):
    d = json.loads(raw)
    fam = d.get("family") or {}
    pa  = d.get("price") or {}
    name = fam.get("name")
    brand = (fam.get("brand") or {}).get("label")
    imgs = fam.get("images") or []
    image = imgs[0]["url"] if imgs else None
    fskus = fam.get("skus") or []
    # composition: take first sku that has fabric specs (same across sizes)
    comp, nat = "", None
    for s in fskus:
        c,n = build_composition(s.get("specifications"))
        if c: comp, nat = c, n; break
    # price/stock per sku
    pmap = {p["code"]: p for p in (pa.get("skus") or [])}
    variants=[]
    prices=[]
    for s in fskus:
        code=s.get("code")
        p=pmap.get(code, {})
        cur=(p.get("currentPrice") or {}).get("value")
        orig=(p.get("originalPrice") or {}).get("value")
        qty=(((p.get("fulfillment") or {}).get("availability") or {}).get("Corporate") or {}).get("Quantity")
        variants.append({
            "sku": code,
            "size": opt(s.get("optionIds"), "SIZE_CD_"),
            "second_range": opt(s.get("optionIds"), "SECOND_SIZE_RANGE_CD_"),
            "colour": opt(s.get("optionIds"), "COLOUR_") or spec(s.get("specifications"),"colour_group_cd"),
            "price": cur,
            "original_price": orig,
            "on_sale": bool(p.get("isOnSale")),
            "qty": qty,
            "in_stock": (qty or 0) > 0,
            "urgent_low": bool(p.get("isUrgentLowStock")),
        })
        if cur: prices.append(cur)
    return {
        "url": d.get("url"), "id": d.get("id"),
        "name": name, "brand": brand, "image": image,
        "composition": comp, "natural_pct": nat,
        "currency": "CAD",
        "price": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "on_sale": any(v["on_sale"] for v in variants),
        "variants": variants,
        "any_in_stock": any(v["in_stock"] for v in variants),
        "familyStatus": d.get("familyStatus"), "priceStatus": d.get("priceStatus"),
    }

def run(url, wait=16):
    """Navigate the PDP and CAPTURE the page's own XHR responses via CDP Network.

    The page's productFamily / PriceAvailability calls succeed at 200 with the site's
    own (cookie/edge-supplied) auth. Replaying them with fetch() from the page context
    hits 401/400 because a header the app injects is missing — so DON'T replay, just
    intercept what the app already fetched. This is the reliable rung.
    """
    req = urllib.request.Request(f"{CDP}/json/new?about:blank", method="PUT")
    tab = json.load(urllib.request.urlopen(req, timeout=15))
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=40)
    mid=[0]
    def send(method, params=None):
        mid[0]+=1
        ws.send(json.dumps({"id":mid[0],"method":method,"params":params or {}}))
        return mid[0]
    send("Network.enable"); send("Page.enable"); send("Runtime.enable")
    time.sleep(0.4)
    send("Page.navigate", {"url": url})
    hits=[]  # (requestId, url)
    deadline=time.time()+wait
    while time.time()<deadline:
        try:
            ws.settimeout(2); m=json.loads(ws.recv())
        except Exception:
            continue
        if m.get("method")=="Network.responseReceived":
            u=m["params"]["response"]["url"]
            if "/product/productFamily/" in u and "image" not in u:
                hits.append(("family", m["params"]["requestId"], u))
            elif "PriceAvailability" in u:
                hits.append(("price", m["params"]["requestId"], u))
    combined={"url":url}
    m2=None
    for kind, rid, u in hits:
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
                if kind=="family": combined["family"]=j
                else: combined["price"]=j
            except Exception:
                pass
    ws.close()
    # derive id from url
    mm=__import__("re").search(r"-([0-9]+f)\.html", url, __import__("re").I)
    combined["id"]=mm.group(1) if mm else None
    return parse(json.dumps(combined))

if __name__=="__main__":
    urls=sys.argv[1:] or [
        "https://www.marks.com/en/pdp/denver-hayes-men-s-50-wash-classic-fit-crewneck-t-shirt-12597467f.html",
        "https://www.marks.com/en/pdp/denver-hayes-men-s-classic-fit-chest-pocket-crewneck-cotton-t-shirt-71223583f.html",
    ]
    res=[run(u) for u in urls]
    print(json.dumps(res, indent=2))
