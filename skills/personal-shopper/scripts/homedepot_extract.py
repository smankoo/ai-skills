#!/usr/bin/env python3
"""homedepot_extract.py — Home Depot Canada: live price + per-store stock + aisle (VPS, stdlib).

Verified 2026-10-12. The VPS gets Akamai 403 on www.homedepot.ca/search, category grids and
/api/search/v1/search, but the product-service API is OPEN over HTTP/1.1 with a full Chrome UA:

  GET https://www.homedepot.ca/api/productsvc/v1/products/<10-digit id>/store/<store>?fields=BASIC_SPA&lang=en

  -> optimizedPrice.displayPrice/wasprice/percentSaving, storeStock.stockLevel, onlineStock.stockLevel,
     aisleBay.aisleLocation/bayLocation, fulfillmentMessages.bopis.displayStatus ("pickUpToday"),
     productStatus/onlineArticleSiteStatus ("D" = discontinued online).
     A product with no displayPrice at that store (e.g. delisted) returns only productStatus.

Notes:
  * Response is gzip even without Accept-Encoding sometimes -> always decompress.
  * HTTP 500 with a tiny body = unknown/invalid product id (not a wall).
  * Default store 7021 = Burlington (3050 Davidson Ct). Find ids: iMac hd_search.js (search API), or
    web_search "site:homedepot.ca/product <words>" — the id is the URL's last path segment.
  * The API gives no product name; pass a full /product/<slug>/<id> URL to get a readable slug name.

Usage:
  python3 homedepot_extract.py <id|product-url> [...] [--store 7021]
Prints a JSON array: {id, store, slug, price, was, saving_pct, store_stock, online_stock,
  aisle, bay, pickup, status, discontinued_online}
"""
import gzip, json, re, sys, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def fetch(pid, store):
    u = (f"https://www.homedepot.ca/api/productsvc/v1/products/{pid}/store/{store}"
         "?fields=BASIC_SPA&lang=en")
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json",
                                             "Accept-Encoding": "gzip", "Accept-Language": "en-CA"})
    try:
        r = urllib.request.urlopen(req, timeout=40)
        status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        return status, json.loads(raw)
    except Exception:
        return status, {"_raw": raw[:200].decode("utf8", "replace")}


def val(x):
    return x.get("value") if isinstance(x, dict) else None


def parse(arg, store):
    m = re.search(r"(\d{10})(?:\D*$)", arg)
    pid = m.group(1) if m else arg
    sm = re.search(r"/product/([^/]+)/\d{10}", arg)
    status, j = fetch(pid, store)
    if status != 200:
        return {"id": pid, "store": store, "error": f"HTTP {status}", "body": str(j)[:160]}
    op = j.get("optimizedPrice") or {}
    ab = j.get("aisleBay") or {}
    fm = j.get("fulfillmentMessages") or {}
    return {
        "id": pid, "store": store,
        "store_name": ab.get("storeDisplayName"),
        "slug": sm.group(1) if sm else None,
        "price": val(op.get("displayPrice")),
        "was": val(op.get("wasprice")),
        "saving_pct": op.get("percentSaving"),
        "store_stock": (j.get("storeStock") or {}).get("stockLevel"),
        "online_stock": (j.get("onlineStock") or {}).get("stockLevel"),
        "aisle": ab.get("aisleLocation"), "bay": ab.get("bayLocation"),
        "pickup": (fm.get("bopis") or {}).get("displayStatus"),
        "status": op.get("productStatus"),
        "discontinued_online": j.get("onlineArticleSiteStatus") == "D",
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    store = "7021"
    if "--store" in args:
        i = args.index("--store"); store = args[i + 1]; del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    print(json.dumps([parse(a, store) for a in args], indent=2))
