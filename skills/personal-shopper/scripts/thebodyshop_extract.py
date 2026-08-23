#!/usr/bin/env python3
"""
thebodyshop_extract.py — The Body Shop CA (thebodyshop.ca) product extractor.

The Body Shop CA is a SHOPIFY store (myshopify_domain njstuz-x2.myshopify.com),
CAD, with NO bot wall from the VPS — plain urllib works, no exit node / no Mac.

Two fetches per product, both VPS-side:
  1. /products/<handle>.js   -> title, price/compare_at (CENTS), per-variant stock,
                                type, vendor, featured_image, description(body_html).
  2. /products/<handle>      -> PDP HTML for the INCI ingredient list, which lives in
                                the FIRST <span class="metafield-multi_line_text_field">
                                (the SECOND such span is the "how to use" steps).

Cosmetics, not fabric, so the personal-shopper natural-FIBRE gate is N/A. The analogous
signal is "<NN>% ingredients of natural origin", parsed out of the description prose, plus
the full INCI list for anyone screening ingredients. Both surfaced per product.

Run:
  python3 thebodyshop_extract.py shea-body-butter shea-butter-body-butter
  python3 thebodyshop_extract.py https://thebodyshop.ca/products/shea-body-butter

Output: one JSON object per product with
  {handle, url, title, type, vendor, price, compare_at_price, on_sale, available,
   image, natural_origin_pct, ingredients, variants:[{title,sku,price,available}],
   any_in_stock}

Verified 2026-08-23 on 3 live products.
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://thebodyshop.ca"


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def _handle(arg):
    m = re.search(r"/products/([^/?#]+)", arg)
    return m.group(1) if m else arg.strip()


def _cents(v):
    return round(v / 100.0, 2) if isinstance(v, (int, float)) else None


def extract(arg):
    h = _handle(arg)
    d = json.loads(_get(f"{BASE}/products/{h}.js"))
    html = _get(f"{BASE}/products/{h}", html=True)

    # --- ingredients (INCI): first metafield-multi_line_text_field span ---
    ingredients = None
    spans = re.findall(
        r'<span class="metafield-multi_line_text_field">(.*?)</span>', html, re.S)
    if spans:
        ingredients = re.sub(r"\s+", " ", re.sub("<[^>]+>", "", spans[0])).strip()

    # --- % ingredients of natural origin (from description prose) ---
    desc = re.sub("<[^>]+>", " ", d.get("description", ""))
    m = re.search(r"(\d{1,3})%\s*ingredients of natural origin", desc)
    natural_origin_pct = int(m.group(1)) if m else None

    img = d.get("featured_image")
    if isinstance(img, dict):
        img = img.get("src") or img.get("url")
    if isinstance(img, str) and img.startswith("//"):
        img = "https:" + img

    variants = [{
        "title": v.get("title"),
        "sku": v.get("sku"),
        "price": _cents(v.get("price")),
        "available": v.get("available"),
    } for v in d.get("variants", [])]

    price = _cents(d.get("price"))
    compare = _cents(d.get("compare_at_price"))
    return {
        "handle": h,
        "url": f"{BASE}/products/{h}",
        "title": d.get("title"),
        "type": d.get("type"),
        "vendor": d.get("vendor"),
        "price": price,
        "compare_at_price": compare,
        "on_sale": bool(compare and price and compare > price),
        "available": d.get("available"),
        "image": img,
        "natural_origin_pct": natural_origin_pct,
        "ingredients": ingredients,
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = [extract(a) for a in sys.argv[1:]]
    print(json.dumps(out if len(out) > 1 else out[0], indent=2, ensure_ascii=False))
