#!/usr/bin/env python3
"""
Tilley (CA/US) product extractor — Shopify storefront, NO bot wall (VPS-side urllib).

Tilley (tilley.com) is a Canadian natural-fibre-friendly travel/outdoor brand: iconic
100% cotton hats, organic-cotton tees, linen jersey, merino, etc. It runs on Shopify, so
the standard endpoints are open from the VPS with a plain UA — no exit node, no Mac CDP.

Two sources per product:
  1. /products/<handle>.js  -> title, vendor, type, price/compare_at (CENTS), top-level
     `available`, and variants[] each with option1=Colour / option2=Size, price, and a real
     `available` boolean -> per-size/per-colour stock directly. Also featured_image
     (protocol-relative //cdn.shopify.com/... -> prefix https:).
  2. PDP HTML (Accept: text/html) -> fibre composition. Tilley puts it under a
     "Fabric, Care & Origin" accordion. The value sits after an `<h6>Fabric</h6>` header,
     but the wrapper varies by template:
        - hats:    <div class="specs"><h6>Fabric</h6><p>100% Cotton</p></div>
        - apparel: <h6>Fabric</h6> ... 100% Linen  (loose text / ewa-rteLine wrappers)
     So: anchor on `<h6>Fabric</h6>`, take the text up to the next `<h6>`/accordion end,
     strip tags. Fallback: scan the whole PDP for the first `NN% <fibre>` pattern. Some
     items (e.g. certified-organic tees) state fibre only in prose ("certified organic
     cotton") with no %, so composition may be a phrase, not a percentage — return what's
     there and let natural_pct be None when no % is present.

Usage:
    python3 tilley_extract.py <handle-or-product-url> [<handle-or-product-url> ...]
    e.g. python3 tilley_extract.py t3-wanderer-hat linen-jersey-t-shirt
         python3 tilley_extract.py https://www.tilley.com/products/ltm6-airflo-sun-hat

Discovery (find handles):
    /search/suggest.json?q=<terms>&resources[type]=product&resources[limit]=10
    -> resources.results.products[] with title, handle, url, price, available, image.

Output (JSON array), per product:
  {handle, url, title, vendor, type, price, compare_at_price, on_sale, available,
   composition, natural_pct, image, colors[], sizes[],
   variants:[{color,size,price,compare_at,available}], any_in_stock}

Verified 2026-08-24 on 4 live products:
  t3-wanderer-hat (100% Cotton, natural 100, $99),
  ltm6-airflo-sun-hat (100% Recycled Nylon, natural 0, $99),
  linen-jersey-t-shirt (100% Linen, natural 100, $90),
  organic-crew-t-shirt (certified organic cotton — prose, no %, $28).
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
BASE = "https://www.tilley.com"

# fibres the skill counts as NATURAL (lyocell/Tencel plant-derived -> natural; viscose/
# rayon/modal are semi-synthetic -> synthetic unless told otherwise).
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "lyocell", "tencel",
           "merino", "alpaca", "mohair", "jute", "ramie")


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _handle(arg):
    m = re.search(r"/products/([^/?#.]+)", arg)
    return m.group(1) if m else arg.strip().strip("/")


def _composition(pdp_html):
    """Return the fibre text after the <h6>Fabric</h6> header, or a %-fibre fallback."""
    m = re.search(r"<h6>\s*Fabric\s*</h6>(.*?)(?:<h6>|accordion__content|</details>|Care)",
                  pdp_html, re.S | re.I)
    if m:
        txt = re.sub(r"<[^>]+>", " ", m.group(1))
        txt = re.sub(r"&nbsp;?", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip(" .")
        if txt:
            return txt
    # fallback 1: first fibre-% pattern anywhere on the page — but ONLY if it names a
    # real textile fibre (avoids CSS like "100% repeat-x" / "width:100%").
    fibres = NATURAL + ("nylon", "polyester", "spandex", "elastane", "viscose", "rayon",
                        "acrylic", "modal", "polyamide")
    for m in re.finditer(r"\d{1,3}%\s*(?:recycled\s+)?([A-Za-z]+)", pdp_html):
        if m.group(1).lower() in fibres:
            return m.group(0).strip()
    # fallback 2: prose fibre mention in the .js/PDP description (e.g. certified-organic
    # tees state "certified organic cotton" with no percentage). Return the phrase; the
    # caller's natural_pct stays None because there's no % to sum.
    m = re.search(r"((?:certified\s+)?(?:organic\s+)?(?:%s)[a-z ]{0,25})" % "|".join(NATURAL),
                  pdp_html, re.I)
    return m.group(1).strip() if m else None


def _natural_pct(comp):
    """Sum the natural-fibre percentages in a composition string; None if no % present."""
    if not comp:
        return None
    parts = re.findall(r"(\d{1,3})\s*%\s*((?:recycled\s+)?[A-Za-z]+)", comp, re.I)
    if not parts:
        return None
    tot = 0
    for pct, fib in parts:
        fib = fib.lower()
        # "recycled cotton" is still cotton; "recycled nylon"/"recycled polyester" synthetic
        if any(n in fib for n in NATURAL):
            tot += int(pct)
    return tot


def extract(arg):
    handle = _handle(arg)
    d = json.loads(_get(f"{BASE}/products/{handle}.js"))
    pdp = _get(f"{BASE}/products/{handle}", html=True)
    comp = _composition(pdp)

    variants = []
    for v in d.get("variants", []):
        variants.append({
            "color": v.get("option1"),
            "size": v.get("option2"),
            "price": v["price"] / 100.0,
            "compare_at": (v["compare_at_price"] / 100.0) if v.get("compare_at_price") else None,
            "available": v.get("available"),
        })
    img = d.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    def _uniq(key):
        seen, out = set(), []
        for v in variants:
            k = v[key]
            if k and k not in seen:
                seen.add(k); out.append(k)
        return out

    return {
        "handle": handle,
        "url": f"{BASE}/products/{handle}",
        "title": d.get("title"),
        "vendor": d.get("vendor"),
        "type": d.get("type"),
        "price": d.get("price", 0) / 100.0,
        "compare_at_price": (d["compare_at_price"] / 100.0) if d.get("compare_at_price") else None,
        "on_sale": bool(d.get("compare_at_price") and d["compare_at_price"] > d.get("price", 0)),
        "available": d.get("available"),
        "composition": comp,
        "natural_pct": _natural_pct(comp),
        "image": img,
        "colors": _uniq("color"),
        "sizes": _uniq("size"),
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
            out.append({"arg": a, "error": str(e)})
    print(json.dumps(out, indent=2))
