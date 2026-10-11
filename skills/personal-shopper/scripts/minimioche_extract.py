#!/usr/bin/env python3
"""
mini mioche (minimioche.com) product extractor — Toronto DTC, 100% GOTS-certified
organic cotton for the WHOLE household (baby / toddler / kids 1-14y / tween / teen /
men / women), made in Canada. Single-material brand: essentially everything is 100%
organic cotton, so the natural-fibre gate is effectively always satisfied — but this
script still surfaces the composition line so the rule is *shown* honoured, and flags
the rare non-cotton item (e.g. an accessory) if one appears.

WHICH RUNG WORKS: Shopify JSON (rung 2), pure `urllib`, VPS-side. NO bot wall — no
exit node, no Mac delegation, no CDP. (Verified 2026-09-04.)

  /products/<handle>.js  -> price/compare_at (CENTS), top-level `available`, and a
                            variants[] grid (option1=colour, option2=size) each with
                            price + a real `available` boolean = per-size/per-colour
                            live stock. Composition lives in the `description` HTML
                            (prose: "100% GOTS-certified organic cotton...").
  Currency: the `.js` has NO currency field, but the PDP JSON-LD confirms CAD
            (price 52.0 CAD). `?currency=CAD` param is a no-op (store is CAD-native).
            Prices are already CAD — do NOT treat like Everlane/Naked&Famous (USD).

USAGE:
    python3 minimioche_extract.py <handle-or-product-url> [<handle-or-url> ...]
    # e.g.
    python3 minimioche_extract.py adult-organic-cotton-tshirt short-sleeve-tee-organic

OUTPUT (per product, JSON):
    {handle, title, url, price, compare_at_price, on_sale, available,
     composition, natural_pct, image, colors[], sizes[],
     variants:[{color,size,price,compare_at,available}], any_in_stock}

DISCOVERY of handles:
    web_search "site:minimioche.com <keyword>"   (snippets carry /products/<handle>)
    or a collection: /collections/<slug>/products.json?limit=N  -> products[].handle
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://minimioche.com"

# fibres counted as natural (lyocell/Tencel is plant-derived -> natural; viscose/rayon -> synthetic)
NATURAL = ("cotton", "wool", "merino", "linen", "silk", "cashmere",
           "hemp", "lyocell", "tencel")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _composition(desc_html):
    """Pull the fibre-content sentence from the description prose and compute natural %."""
    text = re.sub(r"<[^>]+>", " ", desc_html or "")
    text = re.sub(r"\s+", " ", text).strip()
    # prefer a sentence that names a fibre percentage AND a fibre word
    cand = []
    for seg in re.split(r"[.\n]", text):
        if "%" in seg and any(f in seg.lower() for f in NATURAL + ("polyester", "elastane",
                                                                    "nylon", "spandex",
                                                                    "viscose", "rayon", "modal")):
            cand.append(seg.strip())
    # ignore the marketing "save 15% when you buy 5+" line
    cand = [c for c in cand if "buy" not in c.lower() and "save" not in c.lower()]
    comp = cand[0] if cand else None
    natural_pct = None
    if comp:
        pcts = re.findall(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /-]*)", comp)
        tot = 0
        for pct, fibre in pcts:
            if any(f in fibre.lower() for f in NATURAL):
                tot += int(pct)
        natural_pct = tot if pcts else None
    # single-material brand fallback: "100% GOTS-certified organic cotton" with no explicit %-parse
    if natural_pct is None and re.search(r"100%\s*GOTS", text, re.I):
        comp = comp or "100% GOTS-certified organic cotton"
        natural_pct = 100
    return comp, natural_pct


def extract(handle_or_url):
    h = handle_or_url
    if h.startswith("http"):
        m = re.search(r"/products/([^/?#.]+)", h)
        h = m.group(1) if m else h
    js = json.loads(_get(f"{BASE}/products/{h}.js"))
    variants = []
    colors, sizes = [], []
    for v in js.get("variants", []):
        c, s = v.get("option1"), v.get("option2")
        variants.append({"color": c, "size": s,
                         "price": (v.get("price") or 0) / 100.0,
                         "compare_at": (v.get("compare_at_price") or 0) / 100.0 or None,
                         "available": bool(v.get("available"))})
        if c and c not in colors:
            colors.append(c)
        if s and s not in sizes:
            sizes.append(s)
    comp, nat = _composition(js.get("description", ""))
    img = js.get("featured_image")
    if img and img.startswith("//"):
        img = "https:" + img
    price = (js.get("price") or 0) / 100.0
    cmp_at = (js.get("compare_at_price") or 0) / 100.0 or None
    return {
        "handle": h,
        "title": js.get("title"),
        "url": f"{BASE}/products/{h}",
        "price": price,                       # CAD
        "compare_at_price": cmp_at,           # CAD, when on sale
        "on_sale": bool(cmp_at and cmp_at > price),
        "available": bool(js.get("available")),
        "composition": comp,
        "natural_pct": nat,
        "image": img,
        "colors": colors,
        "sizes": sizes,
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    out = []
    for a in sys.argv[1:]:
        try:
            out.append(extract(a))
        except Exception as e:
            out.append({"input": a, "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))
