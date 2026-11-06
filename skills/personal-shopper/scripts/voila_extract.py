#!/usr/bin/env python3
"""Voila (Sobeys online grocery, voila.ca) product search through its public JSON API. Stdlib only, VPS.
It also covers FARM BOY private-label goods (Farm Boy is Sobeys-owned, and farmboy.ca "Shop online" links to
voila.ca/categories/farm-boy/WEB1146400). FreshCo has no online catalogue; use flipp_extract.py.

Usage:
  voila_extract.py "query" [max] [--brand "Farm Boy"] [--ads]   (sponsored tiles skipped unless --ads)
Examples:
  voila_extract.py "2% milk 4l" 5
  voila_extract.py "farm boy hummus" 5 --brand "Farm Boy"
Output: one JSON line per product: name, brand, size, price, unit_price, promo_price, promo_unit_price,
promo text, available, retailerProductId, url, image.
Prices are Voila's online (GTA fulfilment centre) prices. They are usually close to, but not always the same
as, in-store Sobeys prices. No postal code or store is needed for browse.

PITFALL: a short UA such as "Mozilla/5.0 Chrome/128" gets HTTP 403. Send a full desktop Chrome UA (below).
Verified 2026-10-08.
"""
import json, sys, urllib.request, urllib.parse

ADS = "--ads" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0 Safari/537.36", "Accept": "application/json", "Accept-Language": "en-CA"}
API = "https://voila.ca/api/webproductpagews/v6/product-pages/search"


def search(q, mx=20, brand=None):
    url = API + "?" + urllib.parse.urlencode({"includeAdditionalPageInfo": "false", "maxPageSize": 60,
                                               "maxProductsToDecorate": 60, "q": q})
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    n = 0
    seen = set()
    for g in d.get("productGroups", []):
        for x in g.get("decoratedProducts", []):
            if x["retailerProductId"] in seen: continue
            seen.add(x["retailerProductId"])
            if x.get("featuredProductCampaign") and not ADS: continue  # sponsored, often off-topic
            if brand and brand.lower() not in (x.get("brand") or "").lower(): continue
            amt = lambda o: (o or {}).get("amount")
            up = x.get("unitPrice") or {}
            pup = x.get("promoUnitPrice") or {}
            print(json.dumps({
                "name": x.get("name"), "brand": x.get("brand"), "size": x.get("packSizeDescription"),
                "price": amt(x.get("price")),
                "unit_price": "%s/%s" % (amt(up.get("price")), up.get("unitName")) if up else None,
                "promo_price": amt(x.get("promoPrice")),
                "promo_unit_price": "%s/%s" % (amt(pup.get("price")), pup.get("unitName")) if pup else None,
                "promo": "; ".join(p.get("description", "") for p in x.get("promotions") or []) or None,
                "available": x.get("available"), "sponsored": bool(x.get("featuredProductCampaign")),
                "id": x.get("retailerProductId"),
                "url": "https://voila.ca/products/%s/details" % (x.get("retailerProductId") or x.get("productId")),
                "image": (x.get("image") or {}).get("src")}, ensure_ascii=False))
            n += 1
            if n >= mx: return


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--ads"]
    br = None
    if "--brand" in a:
        i = a.index("--brand"); br = a[i + 1]; a = a[:i] + a[i + 2:]
    if not a:
        print(__doc__); sys.exit()
    search(a[0], int(a[1]) if len(a) > 1 else 20, br)
