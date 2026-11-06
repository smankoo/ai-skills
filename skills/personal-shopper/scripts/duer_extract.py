#!/usr/bin/env python3
"""
duer_extract.py — extract product data from DUER (duer.com), Vancouver performance-apparel DTC.

DUER is a Shopify store with NO bot wall from the VPS (plain urllib works). Whole-household
natural-fibre-friendly source: cotton/lyocell/linen "performance" denim, chinos, tees, shirts,
plus women's and (small) kids/youth. NOTE the fibre gate: many "denim" styles blend in
COOLMAX/Coolmax polyester (~28%) so they land right AT ~70% cotton — read the actual %.

Two fetches per product (both VPS-side, no auth, no headers beyond a UA):
  1. https://duer.com/products/<handle>.js   -> price/compare (CENTS), per-size stock, image
  2. https://duer.com/en-ca/products/<handle> (Accept: text/html) -> composition
     (first <div class="metafield-rich_text_field"><ul> whose <li>s carry a fibre %)

The .js has NO `currency` field — the store default is CAD on the /en-ca/ storefront; treat
cents as CAD. JSON-LD prices are unreliable/USD — do NOT use them.

Usage:
    python3 duer_extract.py <handle-or-product-url> [<handle-or-url> ...]
    # e.g. python3 duer_extract.py mens-performance-denim-athletic-taper-heritage-rinse

Find handles via a collection feed (no bot wall):
    curl "https://duer.com/collections/mens-stretch-jeans/products.json?limit=20"
    -> products[].handle
or web_search "site:duer.com <keyword>".

Output (per product), one JSON object per line:
  {handle, url, title, price, compare_at_price, on_sale, available, image,
   composition, natural_pct, colors[], sizes[],
   variants:[{option1,option2,price,available,sku}], any_in_stock}
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
BASE = "https://duer.com"

# Natural fibres for the >=70% gate. Lyocell/Tencel is plant-derived -> natural.
# Viscose/rayon/modal are semi-synthetic -> synthetic. COOLMAX/polyester/spandex/
# elastane/lycra/nylon/acrylic -> synthetic.
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell",
           "tencel", "hemp", "merino", "alpaca", "mohair")


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _handle(s):
    s = s.strip()
    m = re.search(r"/products/([^/?#.]+)", s)
    return m.group(1) if m else s


def _composition(html):
    """Return (composition_str, natural_pct) from the fibre UL, or (None, None)."""
    # Every metafield-rich_text_field UL; pick the one whose lis carry a leading fibre %.
    for m in re.finditer(r'<div class="metafield-rich_text_field"><ul>(.*?)</ul>', html, re.S):
        lis = re.findall(r"<li>\s*(\d{1,3})\s*%\s*([^<]+?)\s*</li>", m.group(1))
        if not lis:
            continue
        parts, natural = [], 0
        for pct, fibre in lis:
            pct = int(pct)
            fibre = re.sub(r"\s+", " ", fibre).strip()
            parts.append(f"{pct}% {fibre}")
            if any(nat in fibre.lower() for nat in NATURAL):
                natural += pct
        return ", ".join(parts), natural
    return None, None


def extract(handle_or_url):
    h = _handle(handle_or_url)
    j = json.loads(_get(f"{BASE}/products/{h}.js"))
    html = _get(f"{BASE}/en-ca/products/{h}", html=True)
    comp, nat = _composition(html)

    img = j.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    variants = [{
        "option1": v.get("option1"), "option2": v.get("option2"),
        "price": v.get("price"), "available": v.get("available"),
        "sku": v.get("sku"),
    } for v in j.get("variants", [])]

    return {
        "handle": h,
        "url": f"{BASE}/en-ca/products/{h}",
        "title": j.get("title"),
        "price": j.get("price"),                      # CENTS, CAD
        "compare_at_price": j.get("compare_at_price"),
        "on_sale": bool(j.get("compare_at_price")),
        "available": j.get("available"),
        "image": img,
        "composition": comp,
        "natural_pct": nat,
        "colors": sorted({v.get("option1") for v in j.get("variants", []) if v.get("option1")}),
        "sizes": sorted({v.get("option2") for v in j.get("variants", []) if v.get("option2")}),
        "variants": variants,
        "any_in_stock": any(v.get("available") for v in j.get("variants", [])),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for arg in sys.argv[1:]:
        try:
            print(json.dumps(extract(arg), ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"handle": _handle(arg), "error": str(e)}))
