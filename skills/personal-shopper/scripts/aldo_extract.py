#!/usr/bin/env python3
"""
ALDO (aldoshoes.com, CA) product extractor — pure urllib, runs VPS-side, NO bot wall.

ALDO Canada is a Shopify store, but its footwear PDPs 404 on the standard Shopify
`/products/<handle>.js` / `.json` endpoints (only some accessory/jewelry handles serve
`.js`). The reliable path is the fully-rendered **`/en-ca/products/<handle>` PDP HTML**,
which is static and un-walled from the VPS. It carries:
  - a JSON-LD `ProductGroup` block: one `hasVariant` entry PER SIZE with
    `{name:"<Product> - <size>", sku, image, offers.price, offers.priceCurrency,
     offers.availability}` -> per-size price + stock directly (InStock/OutOfStock).
  - the "Materials" accordion in static HTML (`Material: … Lining: … Sole: …`) — the
    composition the natural-fibre gate needs. Footwear is leather/suede/textile/synthetic,
    NOT fibre-%; judge natural (leather/suede) vs synthetic from these labels.

Note the skill's rule: NEVER order kids' shoes (fit needs in-person measuring). ALDO is
adult footwear/accessories, so this extractor is for the adult track.

Usage:
    python3 aldo_extract.py https://www.aldoshoes.com/en-ca/products/fez-black [more URLs...]

    # A bare handle also works; it's expanded to the en-ca PDP:
    python3 aldo_extract.py fez-black levie-black

Output: one JSON object per URL:
    {url, name, brand, image, currency, price_min, price_max,
     material, lining, sole, materials_raw, natural_material,
     sizes:[{size, sku, price, availability}], any_in_stock}

Example (verified 2026-08-21):
    Fez     -> name "Fez", $170.00 CAD, "Smooth Leather"/lining Synthetic/sole Rubber,
               sizes 7:OOS 7.5:OOS 8..12:InStock 13:OOS 14:OOS
    Levie   -> name "Levie", $225.00 CAD, "Smooth Leather"/sole Rubber,
               sizes 5:OOS 6..9:InStock 10..12:OOS
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# Materials that count as natural for the fibre/leather gate (footwear).
NATURAL_MATERIALS = ("leather", "suede", "nubuck", "cotton", "canvas", "wool",
                     "cork", "jute", "hemp", "linen")


def _norm_url(u):
    if u.startswith("http"):
        return u
    # bare handle -> en-ca PDP
    return "https://www.aldoshoes.com/en-ca/products/" + u.strip("/")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _productgroup(html):
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                        html, re.S):
        try:
            j = json.loads(b)
        except Exception:
            continue
        if j.get("@type") == "ProductGroup":
            return j
        if j.get("@type") == "Product" and j.get("hasVariant"):
            return j
    return None


def _materials(html):
    """Pull the Materials accordion block; returns (raw, material, lining, sole)."""
    m = re.search(r'Materials(.*?)</ul>', html, re.S)
    if not m:
        return None, None, None, None
    seg = re.sub(r'<[^>]+>', ' ', m.group(1))
    seg = re.sub(r'\s+', ' ', seg).strip()
    seg = seg[:300]

    def grab(label):
        mm = re.search(label + r':\s*([A-Za-z /-]+?)(?=\s+(?:Material|Lining|Sole|Insole|Heel)\b|$)',
                       seg)
        return mm.group(1).strip() if mm else None

    return seg, grab("Material"), grab("Lining"), grab("Sole")


def parse(url):
    url = _norm_url(url)
    html = fetch(url)
    pg = _productgroup(html)
    if not pg:
        return {"url": url, "error": "no ProductGroup JSON-LD found"}

    brand = pg.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    sizes = []
    image = None
    currency = None
    prices = []
    for v in pg.get("hasVariant", []):
        o = v.get("offers") or {}
        if isinstance(o, list):
            o = o[0] if o else {}
        nm = v.get("name") or ""
        size = nm.split(" - ")[-1] if " - " in nm else (v.get("size") or "")
        avail = str(o.get("availability") or "").split("/")[-1]  # InStock/OutOfStock
        price = o.get("price")
        if price:
            try:
                prices.append(float(price))
            except ValueError:
                pass
        currency = currency or o.get("priceCurrency")
        image = image or v.get("image")
        sizes.append({"size": size, "sku": v.get("sku"),
                      "price": price, "availability": avail})

    raw, material, lining, sole = _materials(html)
    material_l = (material or "").lower()
    natural = any(k in material_l for k in NATURAL_MATERIALS) if material else None

    return {
        "url": url,
        "name": pg.get("name"),
        "brand": brand or "ALDO",
        "image": image,
        "currency": currency,
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "material": material,
        "lining": lining,
        "sole": sole,
        "materials_raw": raw,
        "natural_material": natural,
        "sizes": sizes,
        "any_in_stock": any(s["availability"] == "InStock" for s in sizes),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = [parse(u) for u in sys.argv[1:]]
    print(json.dumps(out if len(out) > 1 else out[0], indent=2))
