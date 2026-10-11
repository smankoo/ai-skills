#!/usr/bin/env python3
"""Eddie Bauer Canada (eddiebauer.com/en-ca) product extractor — VPS-side, no bot wall.

Shopify store (shop id 4gqgby-g9.myshopify.com). eddiebauer.ca 301s to
www.eddiebauer.com/en-ca (CAD storefront). Everything works with plain urllib:

  * /en-ca/products/<handle>.js      -> title, price/compare_at (CENTS, CAD on /en-ca/),
                                        per-variant (Colour / Fit / Size) `available`, image
  * /en-ca/products/<handle>  (PDP)  -> composition in the static "materials" accordion:
                                        div id="acc-...-materials" > .accordion__body ul li
                                        (first <li>s hold fibre lines, e.g. "100% cotton";
                                        care instructions follow in later <li>s)
  * /en-ca/products.json?limit=250&page=N  -> handle discovery (open, no auth)

Usage:
    python3 eddiebauer_extract.py <handle> [<handle> ...]
    python3 eddiebauer_extract.py ls-eddie-bauers-favorite-flannel-classic-eb001543m

Output: one JSON object per product:
    {"handle":..., "title":..., "price": 145.0, "compare_at": null, "currency":"CAD",
     "composition": ["100% cotton"], "image": "https://...",
     "sizes": {"Blackwatch / Regular / S": true, ...}, "url": ...}

Verified 2026-09-11.
"""
import json
import re
import sys
import urllib.request

BASE = "https://www.eddiebauer.com/en-ca"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

FIBRES = re.compile(
    r"\d+%\s*(?:organic\s+|recycled\s+|pima\s+|merino\s+)?"
    r"(?:cotton|wool|linen|silk|cashmere|hemp|polyester|nylon|acrylic|elastane|"
    r"spandex|viscose|rayon|modal|lyocell|tencel|polyamide|down|leather)",
    re.I,
)


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")


def extract(handle):
    js = json.loads(fetch(f"{BASE}/products/{handle}.js"))
    html = fetch(f"{BASE}/products/{handle}")

    # composition: static "materials" accordion
    comp = []
    m = re.search(r'id="acc-[^"]*-materials".*?<ul>(.*?)</ul>', html, re.S)
    if m:
        for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S):
            text = re.sub(r"<[^>]+>", "", li).strip()
            if FIBRES.search(text):
                comp.append(text)

    img = js.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    return {
        "handle": handle,
        "title": js["title"],
        "price": js["price"] / 100.0,
        "compare_at": (js.get("compare_at_price") or 0) / 100.0 or None,
        "currency": "CAD",  # confirmed on /en-ca/ storefront (Shopify.currency active=CAD)
        "composition": comp,
        "image": img,
        "sizes": {v["title"]: v["available"] for v in js["variants"]},
        "url": f"{BASE}/products/{handle}",
    }


if __name__ == "__main__":
    for h in sys.argv[1:]:
        print(json.dumps(extract(h), indent=2))
