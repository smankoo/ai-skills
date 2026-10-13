#!/usr/bin/env python3
"""mastermind_extract.py — Mastermind Toys (mastermindtoys.com, Shopify, CAD) from the VPS, stdlib only.

Usage:
  python3 mastermind_extract.py search "lego city" [n]     # /search/suggest.json: title, price, available, image, url
  python3 mastermind_extract.py product <handle|url>        # variants (sku, price, compare_at, available), tags, image

Verified 2026-10-13: search via suggest.json is open; /products/<h>.js and /products.json often answer
`429 local_rate_limited` from the VPS egress (seen on several Shopify stores), so `product` tries .js once,
then falls back to the PDP HTML (JSON-LD Product/ProductGroup offers + availability). No store-level stock
online; `available` = ships online.
"""
import json, re, sys, time, urllib.request, urllib.parse, urllib.error

BASE = "https://www.mastermindtoys.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Language": "en-CA,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def search(q, n=10):
    u = (f"{BASE}/search/suggest.json?q={urllib.parse.quote(q)}"
         f"&resources%5Btype%5D=product&resources%5Blimit%5D={min(int(n), 10)}")
    d = json.loads(get(u))
    out = []
    for p in d["resources"]["results"]["products"]:
        out.append({"name": p["title"], "handle": p["handle"], "brand": p.get("vendor"),
                    "price": float(p["price"]) if p.get("price") else None,
                    "was": float(p["compare_at_price_max"]) if p.get("compare_at_price_max") not in (None, "0.00") else None,
                    "available": p.get("available"), "image": p.get("image"),
                    "url": BASE + p["url"].split("?")[0]})
    return out


def product(h):
    h = re.sub(r"^.*/products/", "", h).split("?")[0].split("#")[0].rstrip("/")
    url = f"{BASE}/products/{h}"
    try:
        d = json.loads(get(url + ".js"))
        return {"source": "products.js", "name": d["title"], "handle": h, "url": url, "brand": d.get("vendor"),
                "price": d["price"] / 100, "was": (d["compare_at_price"] or 0) / 100 or None,
                "available": d["available"], "image": ("https:" + d["featured_image"]) if str(d.get("featured_image", "")).startswith("//") else d.get("featured_image"),
                "tags": d.get("tags", [])[:40],
                "variants": [{"sku": v.get("sku"), "title": v.get("title"), "price": v["price"] / 100,
                              "was": (v.get("compare_at_price") or 0) / 100 or None, "available": v["available"]}
                             for v in d["variants"]]}
    except urllib.error.HTTPError as e:
        if e.code != 429:
            raise
    time.sleep(2)
    html = get(url, accept="text/html")
    prods = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except ValueError:
            continue
        for x in (j if isinstance(j, list) else j.get("@graph", [j])):
            if "Product" in str(x.get("@type")):
                prods.append(x)
    if not prods:
        return {"error": "no Product JSON-LD", "url": url}
    p = prods[0]
    offers = p.get("offers") or []
    offers = offers if isinstance(offers, list) else [offers]
    for v in p.get("hasVariant") or []:
        o = v.get("offers") or []
        offers += o if isinstance(o, list) else [o]
    img = p.get("image")
    img = img[0] if isinstance(img, list) else (img.get("url") if isinstance(img, dict) else img)
    brand = p.get("brand")
    vs = [{"sku": o.get("sku"), "price": float(o["price"]) if o.get("price") else None,
           "available": str(o.get("availability", "")).endswith("InStock")} for o in offers]
    return {"source": "pdp-jsonld", "name": p.get("name"), "handle": h, "url": url,
            "brand": brand.get("name") if isinstance(brand, dict) else brand,
            "price": vs[0]["price"] if vs else None, "was": None,
            "available": any(v["available"] for v in vs), "image": img, "variants": vs}


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("search", "product"):
        sys.exit(__doc__)
    if sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 10), indent=1))
    else:
        print(json.dumps(product(sys.argv[2]), indent=1))
