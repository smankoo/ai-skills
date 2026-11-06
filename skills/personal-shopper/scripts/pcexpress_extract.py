#!/usr/bin/env python3
"""PC Express (Loblaw family: Fortinos, Real Canadian Superstore, No Frills, Loblaws, Zehrs, ...)
search and store lookup through the public BFF JSON API (api.pcexpress.ca). Stdlib only, runs from the VPS.

Usage:
  pcexpress_extract.py stores <banner> [city-filter]       # list pickup stores (storeId) for a banner
  pcexpress_extract.py search <banner> <storeId> "query" [max]
      [--sponsored keeps ad tiles; dropped by default]
      -> one JSON line per product: name, size, unit price, price, was/sale price, deal text, stock, url, image
Examples:
  pcexpress_extract.py stores fortinos Burlington
  pcexpress_extract.py search fortinos 1495 "2% milk" 10       # Fortinos Appleby Dundas (2515 Appleby Line)
  pcexpress_extract.py search superstore 1511 "basmati rice"
  pcexpress_extract.py search nofrills 3643 "paneer"
Banner ids: fortinos, superstore, nofrills, loblaw, zehrs, independent, valumart, ...
The x-apikey below is the public web key the sites embed in their JS (verified 2026-10-08). If it
starts returning 401 invalid_client, grab the current one from any banner site's network tab
(header `x-apikey` on requests to api.pcexpress.ca).
"""
import json, sys, urllib.request, datetime

API = "https://api.pcexpress.ca/pcx-bff/api"
KEY = "C1xujSegT5j3ap3yexJjqhOfELwGKYvz"
KEEP_SPONSORED = "--sponsored" in sys.argv
SITES = {"fortinos": "www.fortinos.ca", "superstore": "www.realcanadiansuperstore.ca",
         "nofrills": "www.nofrills.ca", "loblaw": "www.loblaws.ca", "zehrs": "www.zehrs.ca"}


def hdrs(banner):
    site = SITES.get(banner, "www.%s.ca" % banner)
    return {"x-apikey": KEY, "Site-Banner": banner, "Content-Type": "application/json",
            "Accept": "application/json", "Accept-Language": "en", "Origin": "https://" + site,
            "Referer": "https://%s/" % site, "x-application-type": "Web",
            "x-loblaw-tenant-id": "ONLINE_GROCERIES", "Business-User-Agent": "PCXWEB",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}


def req(url, banner, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=hdrs(banner), method="POST" if data else "GET")
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


def stores(banner, filt=""):
    for s in req(API + "/v1/pickup-locations?bannerIds=" + banner, banner):
        a = s.get("address") or {}
        line = "%s | %s | %s, %s %s | shoppable=%s" % (s["storeId"], s["name"], a.get("line1"),
                                                        a.get("town"), a.get("postalCode"), s.get("isShoppable"))
        if filt.lower() in line.lower():
            print(line)


def search(banner, store, q, mx=20):
    body = {"cart": {"cartId": ""},
            "fulfillmentInfo": {"storeId": store, "pickupType": "STORE", "offerType": "OG",
                                "date": datetime.date.today().strftime("%d%m%Y"), "timeSlot": None},
            "listingInfo": {"filters": {}, "sort": {}, "pagination": {"from": 1}, "includeFiltersInResponse": False},
            "banner": banner, "userData": {"domainUserId": "", "sessionId": ""},
            "searchRelatedInfo": {"term": q, "options": []}}
    d = req(API + "/v2/products/search", banner, body)
    tiles = []
    def walk(o):
        if isinstance(o, dict):
            if "productTiles" in o: tiles.extend(o["productTiles"] or [])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(d.get("layout", d))
    site = SITES.get(banner, "www.%s.ca" % banner)
    out = 0
    for t in tiles:
        if not KEEP_SPONSORED and (t.get("sponsoredCreative") or t.get("isSponsored")):
            continue  # ads ride on top of results and are often unrelated (lamb chops for "chicken skewers")
        p = t.get("pricing") or {}
        deal = t.get("deal") or {}
        size = (t.get("packageSizing") or "")
        print(json.dumps({
            "brand": t.get("brand"), "name": t.get("title"),
            "size": size.split(",")[0].strip(), "unit_price": size.split(",", 1)[1].strip() if "," in size else None,
            "price": p.get("price"), "was": p.get("wasPrice"), "member_price": p.get("memberOnlyPrice"),
            "deal": ("%s %s until %s" % (deal.get("type"), deal.get("text"), (deal.get("expiryDate") or "")[:10])) if deal else None,
            "sold_by": (t.get("pricingUnits") or {}).get("type"),
            # inventoryIndicator None = in stock (no flag); else e.g. {indicatorId:'OUT', text:'Out of Stock'}
            "stock": ((t.get("inventoryIndicator") or {}).get("text") or "in stock"),
            "sponsored": bool(t.get("sponsoredCreative") or t.get("isSponsored")),
            "url": "https://%s%s" % (site, t.get("link", "")),
            "image": ((t.get("productImage") or [{}])[0]).get("smallUrl")}, ensure_ascii=False))
        out += 1
        if out >= mx: break
    sys.stderr.write("total results: %s, printed %d\n" % (d.get("searchResultsCount"), out))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--sponsored"]
    if a and a[0] == "stores":
        stores(a[1], a[2] if len(a) > 2 else "")
    elif a and a[0] == "search":
        search(a[1], a[2], a[3], int(a[4]) if len(a) > 4 else 20)
    else:
        print(__doc__)
