#!/usr/bin/env python3
"""RW&CO (rw-co.com) product extractor — Reitmans-family Canadian workwear banner.

Shopify store, NO bot wall, pure urllib from the VPS (verified 2026-09-09).

Two requests per product:
  1. https://www.rw-co.com/products/<handle>.js
       -> title, vendor, price/compare_at_price (CENTS, CAD — store is CA-only,
          `.js` has no currency field), per-variant (colour/size) `available`,
          featured image (protocol-relative //cdn.shopify.com/...).
  2. https://www.rw-co.com/products/<handle>   (PDP HTML, ~1.3 MB)
       -> fabric composition from the static "Materials" accordion
          (`pvt-accordion`): text right after the `</summary>` following the
          word "Materials", e.g. "57% Polyester, 19% viscose, 18% wool, 6% elastane".
       NOT in `.js` (description only teases e.g. "contains 18% wool") and the
       PDP JSON-LD is Organization-only (no Product block).

Discover handles: /products.json?limit=250 (open) or /search/suggest.json.

Run:  python3 rwco_extract.py <handle> [<handle> ...]
Output (one JSON object per line):
  {"handle","title","vendor","price","compare_at_price","currency":"CAD",
   "composition","natural_fibre_pct","image","variants":[{"title","available","sku"}...]}

natural_fibre_pct counts cotton/wool/linen/silk/cashmere/lyocell/tencel/modal? NO —
viscose/rayon/modal count as SYNTHETIC per the household rule; lyocell/TENCEL natural.
"""
import json, re, sys, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
BASE = "https://www.rw-co.com"

NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "merino", "alpaca", "mohair", "leather", "down")

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")

def natural_pct(comp):
    total = 0
    for pct, fibre in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z \-]+)", comp or ""):
        if any(n in fibre.lower() for n in NATURAL):
            total += int(pct)
    return total

def composition(handle):
    h = get(f"{BASE}/products/{handle}")
    i = h.find("Materials")
    while i != -1:
        j = h.find("</summary>", i)
        if j == -1:
            break
        txt = re.sub(r"<[^>]+>", " ", h[j:j + 3000])
        txt = re.sub(r"\s+", " ", txt).strip()
        # cut at Care Instructions if present
        txt = re.split(r"Care Instructions", txt)[0].strip()
        if re.search(r"\d{1,3}\s*%", txt):
            return txt
        i = h.find("Materials", i + 1)
    return None

def extract(handle):
    d = json.loads(get(f"{BASE}/products/{handle}.js"))
    comp = composition(handle)
    img = d.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img
    return {
        "handle": handle,
        "title": d["title"],
        "vendor": d.get("vendor"),
        "price": d["price"] / 100.0,
        "compare_at_price": (d.get("compare_at_price") or 0) / 100.0 or None,
        "currency": "CAD",
        "composition": comp,
        "natural_fibre_pct": natural_pct(comp),
        "image": img,
        "variants": [{"title": v["title"], "available": v["available"], "sku": v.get("sku")}
                     for v in d["variants"]],
    }

if __name__ == "__main__":
    for handle in sys.argv[1:]:
        print(json.dumps(extract(handle), ensure_ascii=False))
