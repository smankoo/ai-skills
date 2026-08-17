#!/usr/bin/env python3
"""
Reitmans (reitmans.com) product extractor — personal-shopper skill.

Reitmans is a Shopify store with NO bot wall from the VPS (plain curl/requests work).
Two data sources are combined:
  1. `/products/<handle>.js`   -> live price (cents), per-variant stock (`available`),
     image, variant grid (Colour / Size / Length options). This is the money endpoint.
  2. `/products/<handle>` HTML -> exact fabric composition, which is NOT in the .js/.json.
     It lives in the "Materials" accordion as a single `<li class="p3">55% Linen, 45% Viscose</li>`.

Prices are in CENTS in the .js endpoint (divide by 100). `compare_at_price` = original
(struck-through) price when on sale.

Sister banners on the same platform (Penningtons, Addition Elle, RW&CO, Hyba) should
transfer — swap the domain.

USAGE
  python3 reitmans_extract.py <product-url-or-handle> [<url-or-handle> ...]

  Accepts either a full PDP URL or a bare handle:
    python3 reitmans_extract.py https://www.reitmans.com/products/wide-leg-linen-pants-women-s-collection-492032
    python3 reitmans_extract.py woven-fit-flare-midi-dress-100-cotton-498128

OUTPUT (one JSON object per product)
  {url, handle, title, vendor, type, price, price_min, price_max, compare_at_price,
   on_sale, available, composition, natural_pct, image,
   colors[], sizes[], lengths[],
   variants:[{title, color, size, length, price, compare_at, available}],
   any_in_stock}

  price/price_min/price_max/compare_at in DOLLARS. natural_pct = summed cotton/linen/
  wool/silk/cashmere/lyocell/modal share (viscose/rayon counted SYNTHETIC per skill rule).

Verified 2026-08-16 on two live products:
  - wide-leg-linen-pants-women-s-collection-492032  -> "55% Linen, 45% Viscose" natural_pct 55
  - woven-fit-flare-midi-dress-100-cotton-498128     -> "100% Cotton" natural_pct 100
Both prices, sale flags, per-variant stock and images matched the live pages.
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
BASE = "https://www.reitmans.com"

# Natural fibres for the natural-fibre gate. Viscose/rayon/modal-adjacent are semi-synthetic;
# per the skill, count viscose/rayon as SYNTHETIC. Lyocell/Tencel is plant-derived -> natural.
NATURAL = ("cotton", "linen", "wool", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "merino", "mohair", "alpaca", "ramie", "jute")


def _get(url, as_json=False):
    # NOTE: Reitmans content-negotiates on Accept. A bare PDP URL with
    # `Accept: application/json` returns the .json product feed, NOT the HTML —
    # so the Materials-accordion composition would be missing. Ask for the
    # right type explicitly: JSON for .js/.json endpoints, text/html otherwise.
    accept = "application/json" if as_json else "text/html,application/xhtml+xml"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if as_json else raw


def _handle(arg):
    if "/products/" in arg:
        h = arg.split("/products/", 1)[1]
        return h.split("?")[0].split("#")[0].rstrip("/")
    return arg.strip().split("?")[0]


def _img(u):
    if not u:
        return None
    return ("https:" + u) if u.startswith("//") else u


def _composition(handle):
    """Fetch the PDP HTML and pull the single <li class="p3"> under the Materials accordion."""
    try:
        html = _get(f"{BASE}/products/{handle}")
    except Exception:
        return None
    # The composition is emitted as a lone p3 list item, e.g. "55% Linen, 45% Viscose".
    for m in re.finditer(r'<li class="p3">([^<]*)</li>', html):
        txt = m.group(1).strip()
        if re.search(r'\d+%', txt):
            return txt
    # Fallback: any "NN% Fibre" run in the page.
    hits = re.findall(r'\d{1,3}%\s*[A-Za-z]+', html)
    return ", ".join(dict.fromkeys(hits)) if hits else None


def _natural_pct(composition):
    if not composition:
        return None
    total = 0
    for pct, fibre in re.findall(r'(\d{1,3})%\s*([A-Za-z]+)', composition):
        if fibre.lower() in NATURAL:
            total += int(pct)
    return total


def extract(arg):
    handle = _handle(arg)
    js = _get(f"{BASE}/products/{handle}.js", as_json=True)
    variants = []
    colors, sizes, lengths = [], [], []
    for v in js.get("variants", []):
        row = {
            "title": v.get("title"),
            "color": v.get("option1"),
            "size": v.get("option2"),
            "length": v.get("option3"),
            "price": round(v["price"] / 100, 2),
            "compare_at": round(v["compare_at_price"] / 100, 2) if v.get("compare_at_price") else None,
            "available": v.get("available"),
        }
        variants.append(row)
        if row["color"] and row["color"] not in colors:
            colors.append(row["color"])
        if row["size"] and row["size"] not in sizes:
            sizes.append(row["size"])
        if row["length"] and row["length"] not in lengths:
            lengths.append(row["length"])

    comp = _composition(handle)
    cap = js.get("compare_at_price")
    return {
        "url": f"{BASE}/products/{handle}",
        "handle": handle,
        "title": js.get("title"),
        "vendor": js.get("vendor"),
        "type": js.get("type"),
        "price": round(js["price"] / 100, 2),
        "price_min": round(js["price_min"] / 100, 2),
        "price_max": round(js["price_max"] / 100, 2),
        "compare_at_price": round(cap / 100, 2) if cap else None,
        "on_sale": bool(cap and cap > js["price"]),
        "available": js.get("available"),
        "composition": comp,
        "natural_pct": _natural_pct(comp),
        "image": _img(js.get("featured_image")),
        "colors": colors,
        "sizes": sizes,
        "lengths": lengths,
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for arg in sys.argv[1:]:
        try:
            out.append(extract(arg))
        except Exception as e:
            out.append({"input": arg, "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
