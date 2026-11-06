#!/usr/bin/env python3
"""
kitandace_extract.py — extract a Kit and Ace (kitandace.com) product for the
personal-shopper skill: name, live CAD price, per-size stock, image, and fibre
composition (for the natural-fibre gate).

Kit and Ace is a Vancouver DTC brand on Shopify. NO bot wall — plain urllib
from the VPS works (no exit node, no Mac delegation). Two cheap requests:
  1. /products/<handle>.js       -> price (CENTS), compare_at, per-variant stock, image
  2. /products/<handle> (HTML)   -> fibre % from the "Fabric • Care" accordion

The store is CAD by default (Shopify.country="CA"); the .js `currency` field is
null and a ?currency= param is IGNORED, so hard-code CAD. Composition is NOT in
the .js — it lives only in the static PDP HTML.

Usage:
    python3 kitandace_extract.py <handle-or-product-url> [more...]
    # e.g. python3 kitandace_extract.py 8372351336644-cotton-cashmere-crewneck

Output (per product, JSON):
    {handle, url, title, price, compare_at_price, on_sale, currency, available,
     composition, natural_pct, image,
     colors[], sizes[], variants:[{color,size,price,available}], any_in_stock}
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://www.kitandace.com"

# Natural fibres for the >=~70% gate. Viscose/rayon/modal are semi-synthetic ->
# count as synthetic unless told otherwise. Lyocell/TENCEL is plant-derived ->
# natural.
NATURAL = ("cotton", "wool", "merino", "cashmere", "silk", "linen", "hemp",
           "lyocell", "tencel", "alpaca", "mohair")


def _get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def handle_from(arg):
    arg = arg.strip()
    m = re.search(r"/products/([^/?#.]+)", arg)
    return m.group(1) if m else arg


def parse_composition(html):
    """Fibre string from the 'Fabric • Care' accordion: first <p> under
    <div class="accordion_details"> that contains a %."""
    for m in re.finditer(r'<div class="accordion_details">\s*<p[^>]*>([^<]*)</p>', html):
        txt = re.sub(r"\s+", " ", m.group(1)).strip()
        if "%" in txt:
            return txt
    # fallback: any <p> with several fibre-% tokens
    for m in re.finditer(r"<p[^>]*>([^<]*%[^<]*)</p>", html):
        txt = re.sub(r"\s+", " ", m.group(1)).strip()
        if re.search(r"\d{1,3}%\s*[A-Za-z]", txt):
            return txt
    return None


def natural_pct(comp):
    if not comp:
        return None
    total = 0
    for pct, fib in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z ]*)", comp):
        if any(n in fib.lower() for n in NATURAL):
            total += int(pct)
    return total


def extract(handle):
    handle = handle_from(handle)
    url = f"{BASE}/products/{handle}"
    js = json.loads(_get(url + ".js", "application/json"))
    html = _get(url, "text/html")

    comp = parse_composition(html)
    variants = [{
        "color": v.get("option1"),
        "size": v.get("option2"),
        "price": v["price"] / 100.0,
        "available": v["available"],
    } for v in js.get("variants", [])]
    img = js.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    return {
        "handle": handle,
        "url": url,
        "title": js.get("title"),
        "price": js.get("price", 0) / 100.0,
        "compare_at_price": (js.get("compare_at_price") or 0) / 100.0 or None,
        "on_sale": bool(js.get("compare_at_price") and js["compare_at_price"] > js["price"]),
        "currency": "CAD",  # store is CA; .js currency is null, ?currency= ignored
        "available": js.get("available"),
        "composition": comp,
        "natural_pct": natural_pct(comp),
        "image": img,
        "colors": sorted({v["color"] for v in variants if v["color"]}),
        "sizes": sorted({v["size"] for v in variants if v["size"]}),
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for a in sys.argv[1:]:
        try:
            out.append(extract(a))
        except Exception as e:  # noqa
            out.append({"handle": handle_from(a), "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))
