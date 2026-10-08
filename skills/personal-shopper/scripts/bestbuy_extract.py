#!/usr/bin/env python3
"""bestbuy_extract.py — Best Buy Canada (bestbuy.ca) search + product + live availability.

Pure urllib from the VPS (ladder step 1). The HTML site (www.bestbuy.ca/en-ca/...) is Akamai
"Access Denied" 403 to curl, but the site's own JSON APIs on the same host are open, as long as
you send a browser User-Agent (the default Python-urllib UA is tarpitted -> read timeout).

Endpoints (verified 2026-10-08):
  search : /api/v2/json/search?query=<q>&lang=en-CA&page=1&pageSize=<n>
           -> products[]: sku, name, productUrl, regularPrice, salePrice, isClearance, seller, highResImage
  product: /api/v2/json/product/<sku>?lang=en-CA
           -> name, brandName, modelNumber, upcNumber, regularPrice, salePrice, SaleEndDate,
              isProductOnSale, specs, thumbnailImage, additionalMedia[]
  offers : /api/offers/v1/products/<sku>/offers -> [{sellerNameEn, regularPrice, salePrice, isOnSale,
              saleStartDate, isWinner}]  (the "buy box"; marketplace sellers appear here)
  stores : /api/v2/json/locations?lang=en-CA&postalCode=<pc> -> locations[] {locationId, name, distance}
           Burlington = locationId 942 (1200 Brant St); Oakville 930; Oakville Place Express 181
  avail  : /ecomm-api/availability/products?accept=application%2Fvnd.bestbuy.standardproduct.v1%2Bjson
             &accept-language=en-CA&locations=942%7C930&postalCode=<pc>&skus=<sku>%7C<sku>
           -> availabilities[]: shipping{status, quantityRemaining, levelsOfServices[].deliveryDate/price},
              pickup{status, locations[]{locationKey,name,quantityOnHand,hasInventory}}
           Without &locations= the pickup list comes back EMPTY (status NotAvailable) — always pass it.

Usage:
  python3 bestbuy_extract.py search "nintendo switch 2" [n]
  python3 bestbuy_extract.py product <sku-or-PDP-url> [...] [--postal L7M0K5] [--stores 942,930]
"""
import json, re, sys, urllib.parse, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/129.0 Safari/537.36")
BASE = "https://www.bestbuy.ca"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json",
                                                       "Accept-Language": "en-CA"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def search(q, n=10):
    d = get("/api/v2/json/search?" + urllib.parse.urlencode(
        {"query": q, "lang": "en-CA", "page": 1, "pageSize": n}))
    return {"total": d.get("total"), "products": [{
        "sku": p["sku"], "name": p["name"], "url": BASE + p["productUrl"],
        "regular_price": p.get("regularPrice"), "sale_price": p.get("salePrice"),
        "on_sale": (p.get("salePrice") or 0) < (p.get("regularPrice") or 0),
        "clearance": p.get("isClearance"), "seller": (p.get("seller") or {}).get("name") or "Best Buy",
        "image": p.get("highResImage") or p.get("thumbnailImage")} for p in d.get("products", [])]}


def product(sku, postal="L7M0K5", stores=("942", "930")):
    sku = re.search(r"(\d{7,9})/?$", sku.split("?")[0]).group(1)
    p = get(f"/api/v2/json/product/{sku}?lang=en-CA")
    try:
        offers = get(f"/api/offers/v1/products/{sku}/offers")
    except Exception:
        offers = []
    win = next((o for o in offers if o.get("isWinner")), offers[0] if offers else {})
    a = get("/ecomm-api/availability/products?accept=application%2Fvnd.bestbuy.standardproduct.v1%2Bjson"
            f"&accept-language=en-CA&locations={'%7C'.join(stores)}&postalCode={postal}&skus={sku}")
    av = (a.get("availabilities") or [{}])[0]
    sh, pu = av.get("shipping") or {}, av.get("pickup") or {}
    los = (sh.get("levelsOfServices") or [{}])[0]
    reg, sale = win.get("regularPrice", p.get("regularPrice")), win.get("salePrice", p.get("salePrice"))
    img = (p.get("additionalMedia") or [{}])[0].get("url") or p.get("thumbnailImage")
    return {
        "sku": sku, "url": p.get("productUrl"), "name": p.get("name"), "brand": p.get("brandName"),
        "model": p.get("modelNumber"), "upc": p.get("upcNumber"), "currency": "CAD",
        "regular_price": reg, "sale_price": sale, "on_sale": bool(sale and reg and sale < reg),
        "sale_end": p.get("SaleEndDate"), "seller": win.get("sellerNameEn"),
        "image": img.replace("/500x500/", "/1500x1500/") if img else None,
        "ship_status": sh.get("status"), "ship_qty": sh.get("quantityRemaining"),
        "ship_eta": los.get("deliveryDate"), "ship_cost": los.get("price"),
        "ship_carrier": los.get("carrierName"),
        "pickup_status": pu.get("status"),
        "pickup": [{"store_id": l.get("locationKey"), "store": l.get("name"),
                    "qty": l.get("quantityOnHand"), "in_stock": l.get("hasInventory")}
                   for l in pu.get("locations") or []],
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    postal, stores = "L7M0K5", ("942", "930")
    if "--postal" in args:
        i = args.index("--postal"); postal = args[i + 1].replace(" ", ""); del args[i:i + 2]
    if "--stores" in args:
        i = args.index("--stores"); stores = tuple(args[i + 1].split(",")); del args[i:i + 2]
    if args[0] == "search":
        print(json.dumps(search(args[1], int(args[2]) if len(args) > 2 else 10), indent=1))
    else:
        items = args[1:] if args[0] == "product" else args
        print(json.dumps([product(s, postal, stores) for s in items], indent=1))
