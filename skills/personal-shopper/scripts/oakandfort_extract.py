#!/usr/bin/env python3
"""
oakandfort_extract.py — extract product data from Oak + Fort (oakandfort.com).

Oak + Fort is a Canadian Shopify store with NO bot wall — plain urllib works
from the VPS (no exit node, no Mac delegation). Two fetches per product:

  1. /products/<handle>.js   -> price (CENTS), compare_at_price, per-variant
     colour/size + `available` (real per-size stock), featured image, vendor.
  2. /products/<handle>       -> PDP HTML. The exact fibre composition lives in
     the "Materials & Care" accordion, in the STATIC html (no JS/click needed),
     immediately after the `filter-materials-care-heading` header
     (e.g. "100% Linen" or "55% Linen, 45% Rayon").

Natural-fibre gate: cotton/linen/wool/silk/cashmere/lyocell(TENCEL)/hemp/ramie
count as natural; polyester/nylon/acrylic/elastane/spandex AND viscose/rayon/
modal (semi-synthetic) count as synthetic. Oak + Fort NAMES lie about blends
("Linen Blend Shirt" is 55% linen / 45% rayon = natural_pct 55) — read the %.

USAGE:
  python3 oakandfort_extract.py <product-url-or-handle> [<url2> ...]
    e.g. python3 oakandfort_extract.py \
      https://oakandfort.com/products/linen-button-up-shirt-wt-10427-w

OUTPUT (JSON per URL):
  {url, handle, title, vendor, type, price, compare_at_price, on_sale,
   available, composition, natural_pct, image, colors[], sizes[],
   variants:[{color,size,price,compare_at,available,sku}], any_in_stock,
   care}

Verified 2026-08-31 on:
  - linen-button-up-shirt-wt-10427-w   -> "100% Linen", natural_pct 100
  - linen-blend-button-up-shirt-wt-14134-m -> "55% Linen, 45% Rayon",
    natural_pct 55, $29.99 (compare $98), 3/5 variants in stock
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://oakandfort.com"

NATURAL = ("cotton", "linen", "wool", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "ramie", "merino", "alpaca", "mohair", "jute")
# viscose/rayon/modal are semi-synthetic -> counted synthetic per skill rule.


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _handle(u):
    u = u.strip().rstrip("/")
    if u.startswith("http"):
        m = re.search(r"/products/([^/?#]+)", u)
        return m.group(1) if m else u.rsplit("/", 1)[-1]
    return u


def _composition(html):
    """Pull the fibre line from the Materials & Care accordion (static HTML)."""
    i = html.find("filter-materials-care-heading")
    if i < 0:
        i = html.find("Materials & Care")
    if i < 0:
        return None, None
    seg = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", html[i:i + 1500])).strip()
    seg = seg.replace("Materials & Care", "", 1).strip()
    # Cut off care instructions so they don't get parsed as a fibre name.
    seg = re.split(r"(?i)\b(machine wash|hand wash|dry clean|do not|hang to|"
                   r"cool iron|lay flat|line dry|tumble dry|wash cold|"
                   r"exclusive of|only non-chlorine|wipe clean)\b", seg)[0]
    # composition = "<NN>% Fibre" pairs (fibre = 1-2 words, incl. hyphens)
    pairs = re.findall(
        r"\d{1,3}\s?%\s*[A-Za-z][A-Za-z-]*(?:\s[A-Za-z][A-Za-z-]*)?", seg)
    if not pairs:
        return None, None
    comp = ", ".join(re.sub(r"\s+", " ", p).strip() for p in pairs)
    nat = 0
    for pct, fib in re.findall(r"(\d{1,3})\s?%\s*([A-Za-z][A-Za-z ]*)", comp):
        if any(n in fib.lower() for n in NATURAL):
            nat += int(pct)
    return comp, nat


def extract(url):
    h = _handle(url)
    j = json.loads(_get(f"{BASE}/products/{h}.js"))
    html = _get(f"{BASE}/products/{h}", html=True)
    comp, nat = _composition(html)
    fi = j.get("featured_image")
    if isinstance(fi, dict):
        fi = fi.get("src")
    if isinstance(fi, str) and fi.startswith("//"):
        fi = "https:" + fi
    variants = [{
        "color": v.get("option1"),
        "size": v.get("option2"),
        "price": (v.get("price") or 0) / 100,
        "compare_at": (v.get("compare_at_price") or 0) / 100 or None,
        "available": v.get("available"),
        "sku": v.get("sku"),
    } for v in j.get("variants", [])]
    colors = sorted({v["color"] for v in variants if v["color"]})
    sizes = sorted({v["size"] for v in variants if v["size"]})
    cmp_at = (j.get("compare_at_price") or 0) / 100 or None
    price = (j.get("price") or 0) / 100
    return {
        "url": f"{BASE}/products/{h}",
        "handle": h,
        "title": j.get("title"),
        "vendor": j.get("vendor"),
        "type": j.get("type"),
        "price": price,
        "compare_at_price": cmp_at,
        "on_sale": bool(cmp_at and cmp_at > price),
        "available": j.get("available"),
        "composition": comp,
        "natural_pct": nat,
        "image": fi,
        "colors": colors,
        "sizes": sizes,
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
        "care": None,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for u in sys.argv[1:]:
        try:
            out.append(extract(u))
        except Exception as e:
            out.append({"url": u, "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))
