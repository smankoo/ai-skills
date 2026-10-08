#!/usr/bin/env python3
"""
pharmasave_extract.py — Pharmasave (CA) online shop: search + product page, plain urllib.

Pharmasave's online shop is a nopCommerce multi-store at shop.pharmasave.com. The bare
national catalogue (/store/...) is EMPTY ("All Products (0)"); every franchise store has
its own catalogue + prices at /store<cstoreid>/... . Burlington stores with online shopping
(from pharmasave.com/store-finder StoreLocatorLocations JSON, has_online_shopping=1):
  store9742  Pharmasave WinCare (2501 Guelph Line)   <- default, closest to L7M
  (Plains Road West also has online shopping; find its id in the store-finder JSON)
No bot wall, no JS needed: server-rendered HTML + schema.org Product JSON-LD.

USAGE
  python3 pharmasave_extract.py search "<query>" [--store store9742] [--n 20]
  python3 pharmasave_extract.py pdp <product URL or slug> [--store store9742]
  python3 pharmasave_extract.py stores [--city Burlington]       # which stores sell online

OUTPUT JSON lines. PDP: name, price, old_price (if on sale), availability, sku/UPC, image, url.
Verified 2026-10-08 (store9742: CeraVe Foaming Facial Cleanser 355ML $22.99, AVAILABLE).
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://shop.pharmasave.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept-language": "en-CA"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def money(s):
    m = re.search(r"\$\s*([\d,]+\.\d{2})", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def search(q, store, n=20):
    h = get(f"{BASE}/{store}/search?q={urllib.parse.quote(q)}&pagesize={n}")
    out = []
    for box in h.split('class="product-item"')[1:]:
        a = re.search(r'<h2 class="product-title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', box, re.S)
        if not a:
            continue
        out.append({
            "id": (re.search(r'^\s*data-productid="(\d+)"', box) or [None, None])[1],
            "name": clean(a.group(2)),
            "price": money((re.search(r'class="price actual-price">([^<]+)', box) or [None, ""])[1]),
            "old_price": money((re.search(r'class="price old-price">([^<]+)', box) or [None, ""])[1]),
            "image": (re.search(r'data-lazyloadsrc="([^"]+)"', box) or [None, None])[1],
            "url": BASE + a.group(1),
        })
    return out


def pdp(url, store):
    if not url.startswith("http"):
        url = f"{BASE}/{store}/{url.strip('/')}"
    h = get(url)
    ld = {}
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            j = json.loads(blk, strict=False)
        except ValueError:
            continue
        if j.get("@type") == "Product":
            ld = j
    pid = (re.search(r'id="price-value-(\d+)"', h) or [None, None])[1]
    price_html = (re.search(r'class="product-price">(.*?)</div>', h, re.S) or [None, ""])[1]
    old_html = (re.search(r'class="old-product-price">(.*?)</div>', h, re.S) or [None, ""])[1]
    stock = (re.search(r'id="stock-availability-value-\d+">(.*?)</p>', h, re.S) or [None, ""])[1]
    upc = (re.search(r'id="sku-\d+">([^<]+)', h) or [None, None])[1]
    store_name = clean((re.search(r'You are shopping at\s*(.*?)</', h, re.S) or [None, ""])[1])
    return {
        "id": pid,
        "name": clean(ld.get("name")),
        "price": money(price_html),
        "old_price": money(old_html),
        "availability": clean(stock) or (ld.get("offers") or {}).get("availability"),
        "in_stock": "InStock" in json.dumps(ld.get("offers") or {}),
        "upc": upc,
        "image": ld.get("image"),
        "store": store_name or store,
        "url": url,
    }


def stores(city=None):
    h = get("https://pharmasave.com/store-finder/?shop")
    L = json.loads(re.search(r"StoreLocatorLocations\s*=\s*(\[.*?\]);", h, re.S).group(1))
    for s in L:
        if s.get("has_online_shopping") == "1" and (not city or city.lower() in (s.get("city") or "").lower()):
            yield {"store": "store" + str(s.get("cstoreid") or "").strip(), "name": s.get("name"),
                   "city": s.get("city"), "instacart": s.get("has_instacart") == "1"}


if __name__ == "__main__":
    a = sys.argv[1:]
    store = "store9742"
    if "--store" in a:
        i = a.index("--store"); store = a[i + 1]; del a[i:i + 2]
    n = 20
    if "--n" in a:
        i = a.index("--n"); n = int(a[i + 1]); del a[i:i + 2]
    city = None
    if "--city" in a:
        i = a.index("--city"); city = a[i + 1]; del a[i:i + 2]
    if not a:
        print(__doc__); sys.exit(1)
    if a[0] == "search":
        for r in search(" ".join(a[1:]), store, n):
            print(json.dumps(r, ensure_ascii=False))
    elif a[0] == "pdp":
        for u in a[1:]:
            print(json.dumps(pdp(u, store), ensure_ascii=False))
    elif a[0] == "stores":
        for r in stores(city):
            print(json.dumps(r, ensure_ascii=False))
