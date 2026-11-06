#!/usr/bin/env python3
"""Frank And Oak (frankandoak.com) product extractor.

Canadian mid-market apparel, sustainability/natural-fibre focus (cotton, linen,
hemp, TENCEL/lyocell, pima). It's a Shopify store with NO bot wall from the VPS —
plain urllib works, no exit node, no Mac delegation.

Method (all VPS-side):
  * /products/<handle>.js  -> price (CENTS), compare_at_price, top-level `available`,
    variants[] each with option1=size, price (cents), and a real `available` boolean
    (per-size stock directly), plus `featured_image` and `description` (== body_html).
  * Fabric composition lives in the description/body_html as a "Content: <fibres>"
    line (e.g. "Content: 100% Cotton", "55% Hemp, 45% Organic Cotton"). Parse it and
    compute the natural-fibre share for the natural-fibre gate.
  * Discovery: /products.json?limit=250 lists everything (handle, title, tags), and
    /search/suggest.json is DISABLED (returns empty) — use products.json or
    web_search "site:frankandoak.com <keyword>".

Usage:
  python3 frankandoak_extract.py <handle-or-full-url> [<handle-or-url> ...]
  # e.g. python3 frankandoak_extract.py mens-woven-shirt-canvas-2mwc003fe-clk

Output per product (JSON):
  {url, handle, title, vendor, price, compare_at_price, on_sale, available,
   composition, natural_pct, image, sizes:[{size,price,available}], any_in_stock}

Verified 2026-08-20 on live products:
  mens-knit-t-shirt-moss-green-2mkt0031fe-moss -> "100% Cotton", natural_pct 100, $39.00
  mens-woven-pants-pebble-khaki-2mwp005fe-ekha -> "55% Linen, 45%Cotton", natural_pct 100, in stock
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
BASE = "https://www.frankandoak.com"

# fibres counted as natural (plant/animal). lyocell/tencel is plant-derived -> natural.
# viscose/rayon/modal are semi-synthetic -> count synthetic. spandex/elastane/nylon/
# polyester/acrylic -> synthetic.
NATURAL = ("cotton", "linen", "wool", "silk", "cashmere", "hemp", "lyocell",
           "tencel", "merino", "alpaca", "mohair", "jute", "ramie")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_composition(body_html):
    """Return (composition_str, natural_pct) from the 'Content: ...' line."""
    if not body_html:
        return None, None
    m = re.search(r"Content:\s*([0-9][^<\n]*)", body_html)
    if not m:
        return None, None
    comp = m.group(1).strip().rstrip(".")
    # find each "NN% Fibre" fragment
    parts = re.findall(r"(\d+)\s*%\s*([A-Za-z™\u2122 \-]+)", comp)
    if not parts:
        return comp, None
    natural = 0
    total = 0
    for pct, fibre in parts:
        pct = int(pct)
        total += pct
        fl = fibre.lower()
        if any(n in fl for n in NATURAL):
            natural += pct
    if total == 0:
        return comp, None
    # normalise in case percentages don't sum to 100 exactly
    return comp, round(natural * 100.0 / total)


def extract(handle_or_url):
    if handle_or_url.startswith("http"):
        handle = handle_or_url.rstrip("/").split("/products/")[-1].split("?")[0]
    else:
        handle = handle_or_url
    url = f"{BASE}/products/{handle}"
    js = json.loads(_get(url + ".js"))
    comp, natural_pct = parse_composition(js.get("description", ""))
    sizes = [{"size": v.get("option1"), "price": v["price"] / 100.0,
              "available": v.get("available")} for v in js.get("variants", [])]
    img = js.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img
    return {
        "url": url,
        "handle": handle,
        "title": js.get("title"),
        "vendor": js.get("vendor"),
        "price": js.get("price", 0) / 100.0,
        "compare_at_price": (js.get("compare_at_price") or 0) / 100.0,
        "on_sale": bool(js.get("compare_at_price")
                        and js["compare_at_price"] > js.get("price", 0)),
        "available": js.get("available"),
        "composition": comp,
        "natural_pct": natural_pct,
        "image": img,
        "sizes": sizes,
        "any_in_stock": any(s["available"] for s in sizes),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = [extract(a) for a in sys.argv[1:]]
    print(json.dumps(out if len(out) > 1 else out[0], indent=2, ensure_ascii=False))
