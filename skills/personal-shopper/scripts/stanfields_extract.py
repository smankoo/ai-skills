#!/usr/bin/env python3
"""stanfields_extract.py — Stanfield's (stanfields.com) product extractor.

Nova Scotia heritage underwear/base-layer brand (est. 1856): merino base layers,
cotton underwear/tees, Heritage fleece. Men + women. Strong natural-fibre source
(100% merino, 95% combed-cotton underwear) — but read the %: DRYFX/AIR performance
lines are synthetic, Heritage fleece is 65/35 cotton-poly, "Modal Cotton" is
48% TENCEL / 48% cotton / 4% spandex.

Plain Shopify store, NO bot wall, pure urllib VPS-side. ONE call per product:
  GET https://www.stanfields.com/products/<handle>.js
    -> title, price (CENTS, CAD — store is CA-single-currency, verified via
       Shopify.currency={"active":"CAD"} and PDP JSON-LD priceCurrency),
       per-variant (size/colour) `available`, featured_image,
       AND composition embedded in `description` HTML as "NN% Fibre" runs.
Discover handles via /products.json?limit=250 (open) or /search/suggest.json.

HOW TO RUN (VPS, no deps):
  python3 stanfields_extract.py <handle-or-PDP-url> [...]
  python3 stanfields_extract.py mens-pure-merino-base-layer-top

Output: JSON array on stdout, one object per product:
  {handle, url, title, price, compare_at_price, currency:"CAD", available,
   image, composition, natural_pct, variants:[{title,size,colour,price,available}]}

Verified 2026-09-08 on mens-pure-merino-base-layer-top ($120.00, 100% Merino Wool,
natural 100) and flex-cotton-rib-stretch-trunks-2-pack ($40.00, 95% Combed Cotton /
5% Spandex, natural 95).
"""
import json, re, sys, urllib.request

BASE = "https://www.stanfields.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

NATURAL = {"cotton", "combed cotton", "organic cotton", "wool", "merino", "merino wool",
           "linen", "silk", "cashmere", "hemp", "lyocell", "tencel", "ramie", "jute",
           "mohair", "alpaca", "angora"}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read().decode("utf-8", "replace")

def composition(desc_html):
    """Pull 'NN% Fibre' runs out of the .js description HTML."""
    text = re.sub(r"<[^>]+>", " ", desc_html or "")
    parts = re.findall(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z\- ]{2,30}?)(?=\s*(?:,|/|\d{1,3}\s*%|Care|Wash|Machine|$|\n))", text)
    parts = [(int(p), f.strip().rstrip(".")) for p, f in parts if 0 < int(p) <= 100]
    if not parts:
        return "", None
    comp = ", ".join(f"{p}% {f}" for p, f in parts)
    nat = sum(p for p, f in parts
              if any(k in f.lower() for k in NATURAL) and "polyester" not in f.lower())
    return comp, min(nat, 100)

def extract(handle):
    d = json.loads(get(f"{BASE}/products/{handle}.js"))
    comp, nat = composition(d.get("description"))
    variants = []
    for v in d.get("variants", []):
        variants.append({
            "title": v["title"],
            "size": v.get("option1"),
            "colour": v.get("option2"),
            "price": v["price"] / 100.0,
            "available": bool(v.get("available")),
        })
    img = d.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img
    return {
        "handle": handle,
        "url": f"{BASE}/products/{handle}",
        "title": d.get("title"),
        "price": d.get("price", 0) / 100.0,
        "compare_at_price": (d.get("compare_at_price") or 0) / 100.0 or None,
        "currency": "CAD",
        "available": bool(d.get("available")),
        "image": img,
        "composition": comp,
        "natural_pct": nat,
        "variants": variants,
    }

if __name__ == "__main__":
    args = sys.argv[1:] or ["mens-pure-merino-base-layer-top",
                            "flex-cotton-rib-stretch-trunks-2-pack"]
    handles = [re.sub(r".*?/products/([^/?#.]+).*", r"\1", a) for a in args]
    print(json.dumps([extract(h) for h in handles], indent=2))
