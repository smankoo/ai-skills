#!/usr/bin/env python3
"""Province of Canada extractor — Shopify storefront, NO bot wall, pure urllib (VPS-side).

Province of Canada (provinceofcanada.com) is a Canadian brand: made-in-Canada basics,
heavy on organic/GOTS cotton — a strong natural-fibre source. It's a standard Shopify
store, so all the storefront JSON endpoints are open from the VPS (no Cloudflare, no
PerimeterX, no exit node, no Mac delegation).

Which rung: Shopify JSON (rung 2), all VPS-side.
- /products/<handle>.js  -> price/compare_at (CENTS), per-size `available` bool, images.
- /products/<handle>.json body_html -> fibre composition ("100% GOTS certified organic
  ... cotton", "80% cotton, 20% Polyester"). NOT in the .js.
- PDP HTML JSON-LD ProductGroup -> price in CAD + per-variant availability + image (a
  cross-check / alternative to .js; also the only place currency is stated as CAD).

NOTE: the .js `price_currency`/variant `price_currency` fields come back None, but the
site is Canadian and the JSON-LD offers say priceCurrency: CAD. Treat .js prices as CAD.

Usage:
    python3 provinceofcanada_extract.py <handle-or-product-url> [<handle-or-url> ...]
Example:
    python3 provinceofcanada_extract.py bc-lions-cfl-x-the-tragically-hip-tee
    python3 provinceofcanada_extract.py https://provinceofcanada.com/products/<handle>

Output per URL (JSON):
    {handle, url, title, price, compare_at_price, on_sale, currency, available,
     composition, natural_pct, image, sizes:[{size,available}], any_in_stock}

Find candidate handles via:  web_search "site:provinceofcanada.com <keyword>"
or list them:  curl .../products.json?limit=250  -> products[].handle
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://provinceofcanada.com"

# fibres counted as NATURAL for the natural-fibre gate. Viscose/rayon/modal = synthetic.
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "merino",
           "lyocell", "tencel", "alpaca", "mohair", "jute", "ramie")
SYNTH = ("polyester", "nylon", "acrylic", "elastane", "spandex", "viscose",
         "rayon", "modal", "polyamide", "acetate")


def _get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def handle_of(arg):
    m = re.search(r"/products/([^/?#.]+)", arg)
    return m.group(1) if m else arg.strip()


def parse_composition(body_html):
    """Return (raw_string, natural_pct or None) from a product body_html.

    Province of Canada phrases fibre content freely, e.g.
      "100% GOTS certified organic 200gsm cotton, knitted locally"
      "80% cotton, 20% Polyester"
    So: find each "NN%" and grab the FIRST fibre keyword within ~40 chars after it.
    """
    txt = re.sub(r"<[^>]+>", " ", body_html or "")
    txt = re.sub(r"\s+", " ", txt).replace("\xa0", " ")
    fibre_re = re.compile("|".join(NATURAL + SYNTH), re.I)
    parts, nat, seen_pct = [], 0, False
    for m in re.finditer(r"(\d{1,3})\s*%", txt):
        window = txt[m.end():m.end() + 45]
        fm = fibre_re.search(window)
        if not fm:
            continue
        seen_pct = True
        pct = int(m.group(1))
        fib = fm.group(0)
        fl = fib.lower()
        is_nat = any(n in fl for n in NATURAL) and not any(s in fl for s in SYNTH)
        if is_nat:
            nat += pct
        parts.append(f"{pct}% {fib.title()}")
    if not seen_pct:
        return None, None
    return ", ".join(parts), nat


def extract(arg):
    h = handle_of(arg)
    out = {"handle": h, "url": f"{BASE}/products/{h}"}
    try:
        js = json.loads(_get(f"{BASE}/products/{h}.js", "application/json"))
    except Exception as e:
        out["error"] = f".js fetch failed: {e}"
        return out
    out["title"] = js.get("title")
    out["price"] = round(js.get("price", 0) / 100, 2)
    cap = js.get("compare_at_price")
    out["compare_at_price"] = round(cap / 100, 2) if cap else None
    out["on_sale"] = bool(cap and cap > js.get("price", 0))
    out["currency"] = "CAD"  # .js states None; JSON-LD offers say CAD
    out["available"] = js.get("available")
    fi = js.get("featured_image") or ""
    out["image"] = ("https:" + fi) if fi.startswith("//") else fi
    sizes = []
    for v in js.get("variants", []):
        sizes.append({"size": v.get("option1") or v.get("title"),
                      "available": v.get("available")})
    out["sizes"] = sizes
    out["any_in_stock"] = any(s["available"] for s in sizes)
    # composition from .json body_html
    try:
        pj = json.loads(_get(f"{BASE}/products/{h}.json", "application/json"))["product"]
        comp, nat = parse_composition(pj.get("body_html"))
        out["composition"] = comp
        out["natural_pct"] = nat
    except Exception as e:
        out["composition"] = None
        out["natural_pct"] = None
        out["_comp_err"] = str(e)
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    res = [extract(a) for a in argv]
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
