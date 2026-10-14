#!/usr/bin/env python3
"""Visions Electronics (visions.ca, Canada, electronics/appliances): search + PDP, plain urllib (VPS).

Usage:
  python3 visions_extract.py search "sony headphones" [N]     # Algolia hits: name, price, url, image, stock
  python3 visions_extract.py pdp <product-url>                # JSON-LD Product (price, availability) + store stock hints

Method (verified 2026-10-14):
  * Magento 2 + Algolia. The homepage HTML carries `algoliaConfig=JSON.parse('...')` with applicationId
    (ROBTRSQZ7A), indexName (visions_productiondefault) and a SECURED search apiKey that embeds
    `validUntil=<epoch>` (about 24 h). Never hardcode the key: fetch the homepage and parse it each run.
  * Search: POST https://<APP>-dsn.algolia.net/1/indexes/<index>/query with X-Algolia-Application-Id/API-Key.
  * /search?q= is a 404; Magento's search URL is /catalogsearch/result?q=.
"""
import json, re, sys, urllib.request, html as H

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")


def algolia_cfg():
    h = get("https://www.visions.ca/")
    m = re.search(r"algoliaConfig\s*=\s*JSON\.parse\('(.*?)'\)", h, re.S)
    raw = m.group(1).encode().decode("unicode_escape")
    return json.loads(raw)


def search(q, n=10):
    c = algolia_cfg()
    app, key, idx = c["applicationId"], c["apiKey"], c["indexName"] + "_products"
    body = json.dumps({"params": f"query={urllib.request.quote(q)}&hitsPerPage={n}"}).encode()
    req = urllib.request.Request(f"https://{app}-dsn.algolia.net/1/indexes/{idx}/query", data=body,
                                 headers={"X-Algolia-Application-Id": app, "X-Algolia-API-Key": key,
                                          "Content-Type": "application/json", "User-Agent": UA})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    out = []
    for h in d.get("hits", []):
        price = h.get("price")
        if isinstance(price, dict):
            cad = price.get("CAD", {})
            price = cad.get("default"), cad.get("default_original_formated") or cad.get("default_formated")
        out.append({"name": h.get("name"), "sku": h.get("sku"), "price": price, "in_stock": h.get("in_stock"),
                    "url": h.get("url"), "image": h.get("image_url") or h.get("thumbnail_url")})
    return {"nbHits": d.get("nbHits"), "hits": out}


def pdp(url):
    h = get(url)
    prod = None
    for blk in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            j = json.loads(blk)
        except ValueError:
            continue
        for x in (j if isinstance(j, list) else j.get("@graph", [j])):
            if isinstance(x, dict) and x.get("@type") == "Product":
                prod = x
    if not prod:
        return {"error": "no Product JSON-LD", "bytes": len(h)}
    off = prod.get("offers") or {}
    off = off[0] if isinstance(off, list) else off
    og = re.search(r'property="og:image" content="([^"]+)', h)
    pid = re.search(r'id="product-price-(\d+)"', h)
    reg = re.search(r'data-price-type="oldPrice"[^>]*>\s*<span class="price">\$([\d,.]+)', h)
    res = {"name": H.unescape(prod.get("name") or ""), "sku": prod.get("sku"), "brand": (prod.get("brand") or {}).get("name") if isinstance(prod.get("brand"), dict) else prod.get("brand"),
            "price": off.get("price"), "currency": off.get("priceCurrency"),
            "regular_price": reg.group(1) if reg else None,
            "availability": (off.get("availability") or "").rsplit("/", 1)[-1],
            "image": (prod.get("image") if isinstance(prod.get("image"), str) else (prod.get("image") or [None])[0]) or (og and og.group(1)),
            "url": url, "product_id": pid.group(1) if pid else None}
    if pid:
        res["stores"] = stores(pid.group(1))
    return res


def stores(product_id):
    """Magento REST (Amasty store pickup MSI), open to anonymous GET: per-store qty for one product id."""
    req = urllib.request.Request(f"https://www.visions.ca/rest/default/V1/amstorepickup_msi/{product_id}/getLocationsByProduct",
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return [{"store": i["location"]["name"], "city": i["location"].get("city"), "qty": i.get("qty")} for i in d.get("items", [])]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10), indent=1))
    else:
        print(json.dumps(pdp(sys.argv[2]), indent=1))
