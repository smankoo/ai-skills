#!/usr/bin/env python3
"""
Naked & Famous Denim (nakedandfamousdenim.com) product extractor.

Montreal-based premium selvedge-denim maker (Shopify). NO bot wall — pure urllib
from the VPS works. A SINGLE `/products/<handle>.js` call returns price, per-size
stock, image, AND the fibre composition (it's embedded in the `description` field
as an `<li>` bullet, e.g. "98% Cotton / 2% Elastane"). No separate HTML fetch or
JSON-LD parse needed.

Top natural-fibre source for men's denim/tees: raw selvedge is almost always
100% cotton; "stretch" cuts add ~1-2% elastane (still clears a 70% rule easily).
The fibre % is only stated when it matters — read it, don't assume 100%.

Usage:
    python3 nakedandfamous_extract.py <handle-or-product-url> [<handle-or-url> ...]

Find handles via:  https://www.nakedandfamousdenim.com/products.json?limit=250
or web_search "site:nakedandfamousdenim.com <keyword>".

Example output (one dict per URL):
    {
      "handle": "true-guy-11oz-stretch-selvedge",
      "title": "True Guy - 11oz Stretch Selvedge",
      "url": "https://www.nakedandfamousdenim.com/products/true-guy-11oz-stretch-selvedge",
      "price": 175.0, "currency": "CAD", "compare_at": null, "on_sale": false,
      "available": true,
      "composition": "98% Cotton / 2% Elastane", "natural_pct": 98,
      "image": "https://cdn.shopify.com/...jpg",
      "sizes": [{"size": "27", "price": 175.0, "available": true}, ...],
      "any_in_stock": true
    }
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://www.nakedandfamousdenim.com"
# NOTE: Shopify .js gives no currency; store bills in CAD on the .com storefront.
CURRENCY = "CAD"

# Natural fibres per the skill's rule. Viscose/rayon/modal count as SYNTHETIC.
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "lyocell",
           "tencel", "merino", "alpaca", "mohair", "ramie", "jute")


def handle_from(arg):
    m = re.search(r"/products/([^/?#.]+)", arg)
    return m.group(1) if m else arg.strip().rstrip("/")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def parse_composition(description):
    """Pull the fibre bullet from the description HTML. Returns (text, natural_pct)."""
    text = re.sub(r"\s+", " ", description or "")
    # Prefer an <li> that carries a % (that's the fibre line on N&F PDPs)
    cand = None
    for li in re.findall(r"<li>([^<]*%[^<]*)</li>", description or ""):
        li = re.sub(r"\s+", " ", li).replace("\xa0", " ").strip()
        if re.search(r"\d{1,3}\s*%\s*[A-Za-z]", li):
            cand = li
            break
    if not cand:
        # fall back to any "NN% Fibre" run in the prose
        m = re.search(r"(\d{1,3}\s*%\s*[A-Za-z][A-Za-z /%\d]*)", text)
        cand = m.group(1).strip() if m else None
    if not cand:
        return None, None
    cand = re.sub(r"\s*/\s*", " / ", cand).strip()
    natural = 0
    for pct, fibre in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z]+)", cand):
        if any(fibre.lower().startswith(n) for n in NATURAL):
            natural += int(pct)
    # A raw-denim / tee page often just says the fabric without a %, meaning 100%
    if not re.search(r"\d%", cand):
        return cand, None
    return cand, natural


def extract(handle):
    handle = handle_from(handle)
    url = f"{BASE}/products/{handle}"
    p = json.loads(fetch(url + ".js"))
    comp, nat = parse_composition(p.get("description", ""))
    img = p.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img
    sizes = [{"size": v.get("title"),
              "price": round(v["price"] / 100, 2),
              "available": bool(v.get("available"))}
             for v in p.get("variants", [])]
    cmp_at = p.get("compare_at_price")
    return {
        "handle": handle,
        "title": p.get("title"),
        "url": url,
        "price": round(p["price"] / 100, 2),
        "currency": CURRENCY,
        "compare_at": round(cmp_at / 100, 2) if cmp_at else None,
        "on_sale": bool(cmp_at and cmp_at > p["price"]),
        "available": bool(p.get("available")),
        "composition": comp,
        "natural_pct": nat,
        "image": img,
        "sizes": sizes,
        "any_in_stock": any(s["available"] for s in sizes),
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
