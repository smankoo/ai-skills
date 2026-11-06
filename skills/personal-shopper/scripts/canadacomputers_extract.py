#!/usr/bin/env python3
"""canadacomputers_extract.py — Canada Computers & Electronics (canadacomputers.com) from the VPS, stdlib only.

Usage:
  python3 canadacomputers_extract.py search "samsung 990 pro" [n]   # ItemList JSON-LD on the search page -> names + PDP URLs
  python3 canadacomputers_extract.py pdp <url> [--store Burlington]  # price, online status, per-store qty (all ~40 stores)

Verified 2026-10-13 (plain urllib, Chrome UA; no wall):
  * Search: GET /en/search?s=<q> -> `ItemList` JSON-LD (name + url). Prices are not in that list; read each PDP.
  * PDP: `Product` JSON-LD (name, sku, mpn, gtin13, brand, image 800x800, offers.price CAD, availability).
    NB availability is the ONLINE status ("SoldOut" while stores still hold units).
  * Store stock is server-rendered in the "Stock Availability" modal: rows of
      <span class="col-3 ...">Burlington</span> <span class="... shop-online-box ...">3</span> ... data-whid="BL"
    One row per store; the number is units on hand ("0" or "10+" possible).
  * `#onlineinfo` text holds the delivery line ("Sold out online" / "Ships ...").
"""
import html as H, json, re, sys, urllib.parse, urllib.request

BASE = "https://www.canadacomputers.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*",
                                               "Accept-Language": "en-CA,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def lds(t):
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            j = json.loads(m.group(1))
        except ValueError:
            continue
        out += j if isinstance(j, list) else j.get("@graph", [j])
    return out


def search(q, n=20):
    t = get(f"{BASE}/en/search?s={urllib.parse.quote_plus(q)}")
    for x in lds(t):
        if x.get("@type") == "ItemList":
            return [{"name": H.unescape(i.get("name", "")), "url": i.get("url")}
                    for i in x.get("itemListElement", [])][: int(n)]
    return []


def pdp(url, store=None):
    t = get(url)
    p = next((x for x in lds(t) if x.get("@type") == "Product"), None)
    if not p:
        return {"error": "no Product JSON-LD", "url": url}
    o = p.get("offers") or {}
    o = o[0] if isinstance(o, list) else o
    stores = []
    for m in re.finditer(r'<span\s+class="col-3[^"]*">\s*([^<]+?)\s*</span>\s*<span\s+class="[^"]*shop-online-box[^"]*">\s*([^<]*?)\s*</span>'
                         r'(?:\s*<button[^>]*?data-whid="([^"]+)")?', t):
        stores.append({"store": H.unescape(m.group(1)), "qty": m.group(2), "whid": m.group(3)})
    seen, uniq = set(), []
    for s in stores:
        if s["store"] not in seen:
            seen.add(s["store"]); uniq.append(s)
    oi = re.search(r'id="onlineinfo"[^>]*>(.*?)</div>\s*</div>', t, re.S)
    online = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", oi.group(1))).strip() if oi else None
    img = p.get("image")
    r = {"name": H.unescape(p.get("name", "")), "sku": p.get("sku"), "mpn": p.get("mpn"), "gtin": p.get("gtin13"),
         "brand": (p.get("brand") or {}).get("name"), "price": float(o["price"]) if o.get("price") else None,
         "currency": o.get("priceCurrency"), "online_availability": str(o.get("availability", "")).rsplit("/", 1)[-1],
         "online_text": online, "image": img[0] if isinstance(img, list) else img, "url": url,
         "rating": (p.get("aggregateRating") or {}).get("ratingValue"),
         "stores_with_stock": sum(1 for s in uniq if s["qty"] not in ("0", "")), "n_stores": len(uniq)}
    if store:
        r["store"] = next((s for s in uniq if s["store"].lower() == store.lower()), None)
    r["stores"] = uniq
    return r


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("search", "pdp"):
        sys.exit(__doc__)
    if a[0] == "search":
        print(json.dumps(search(a[1], a[2] if len(a) > 2 else 20), indent=1))
    else:
        st = a[a.index("--store") + 1] if "--store" in a else "Burlington"
        print(json.dumps(pdp(a[1], st), indent=1))
