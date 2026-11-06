#!/usr/bin/env python3
"""
la Vie en Rose (CA) product extractor — personal-shopper skill.

WHY: la Vie en Rose (lingerie / sleepwear / loungewear; confirmed in Sumeet's YNAB
history) runs on EPiServer / Optimizely Commerce behind Cloudflare, but the VPS gets
HTTP 200 with the FULL server-rendered HTML — NO bot wall (no exit node, no Mac CDP).
Everything the skill needs comes from a single JSON-LD `ProductGroup` block plus one
small HTML scrape for the exact fibre percentages.

WHAT IT PULLS (per real product, verified 2026-08-19):
  name, brand, category, per-size×colour price + strikethrough (original) price + stock
  (InStock/OutOfStock), image URL, and the exact fibre COMPOSITION with natural-fibre %
  (critical for the natural-fibre gate).

DATA SOURCES:
  * JSON-LD `<script type="application/ld+json">` -> the 2nd block is a `ProductGroup`
    with `hasVariant[]` = one Product per size (each with `size`, `color`, `material`
    (primary fibre only, no %), `image[]`, and `offers{price, priceCurrency,
    availability, priceSpecification.price = StrikethroughPrice}`).
    Placeholder variants for OTHER colourways appear WITHOUT `offers`/`image` — skip them.
  * The exact percentages (e.g. "93% Modal 7% Elastane") are NOT in the JSON-LD's
    `material` field — they live in the details bullet list as a lone
    `<li><p>NN% Fibre ...</p></li>`. Scrape that.

NATURAL-FIBRE RULE: cotton/wool/linen/silk/cashmere/modal/lyocell counted natural;
  polyester/nylon/elastane/spandex/acrylic/viscose*/rayon counted synthetic. (Modal &
  lyocell are plant-derived regenerated cellulose -> counted natural here; viscose/rayon
  counted synthetic per the skill's convention. Flip MODAL_NATURAL below if desired.)

USAGE:
  python3 lavieenrose_extract.py <PDP-URL> [<PDP-URL> ...]
  # discover URLs: web_search 'site:lavieenrose.com/en <category> <keyword>'
  # PDP URL shape: https://www.lavieenrose.com/en/<slug>-<color>-<id>

OUTPUT (one JSON object per URL):
  {url, name, brand, category, composition, natural_pct, primary_material,
   image, colors:[...], strikethrough_price,
   sizes:[{size, color, price, currency, in_stock}], price_range, any_in_stock}
"""
import sys, re, json, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# fibres counted toward the natural-fibre share
NATURAL = {"cotton", "wool", "linen", "silk", "cashmere", "hemp", "modal", "lyocell", "tencel"}
MODAL_NATURAL = True  # set False to count modal/lyocell as synthetic
if not MODAL_NATURAL:
    NATURAL -= {"modal", "lyocell", "tencel"}
FIBRE_RE = (r"cotton|wool|linen|silk|cashmere|hemp|modal|lyocell|tencel|"
            r"polyester|elastane|spandex|nylon|polyamide|acrylic|viscose|rayon")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_composition(html):
    """Return (composition_str, natural_pct) from the lone fibre <li><p> bullet."""
    lis = re.findall(r"<li>\s*<p>([^<]*)</p>\s*</li>", html)
    for t in lis:
        t = t.strip()
        if re.search(r"\d{1,3}\s*%\s*(?:" + FIBRE_RE + ")", t, re.I):
            pairs = re.findall(r"(\d{1,3})\s*%\s*([A-Za-z]+)", t)
            nat = sum(int(p) for p, f in pairs if f.lower() in NATURAL)
            return t, (nat if pairs else None)
    return None, None


def extract(url):
    html = fetch(url)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    pg = None
    for b in blocks:
        try:
            j = json.loads(b)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            pg = j
            break
    if pg is None:
        return {"url": url, "error": "no ProductGroup JSON-LD found"}

    comp, natural_pct = parse_composition(html)
    sizes, colors, prices, strike, image, primary = [], set(), [], None, None, None
    for v in pg.get("hasVariant", []):
        o = v.get("offers")
        if not o:          # placeholder for another colourway — no live data
            continue
        o = o[0] if isinstance(o, list) else o
        price = o.get("price")
        if price is not None:
            prices.append(price)
        sp = o.get("priceSpecification") or {}
        if isinstance(sp, dict) and sp.get("price"):
            strike = sp["price"]
        if v.get("color"):
            colors.add(v["color"])
        if image is None and v.get("image"):
            image = v["image"][0] if isinstance(v["image"], list) else v["image"]
        if primary is None and v.get("material"):
            primary = v["material"]
        sizes.append({
            "size": v.get("size"),
            "color": v.get("color"),
            "price": price,
            "currency": o.get("priceCurrency"),
            "in_stock": str(o.get("availability", "")).split("/")[-1] == "InStock",
        })

    pr = [p for p in prices if p is not None]
    return {
        "url": url,
        "name": pg.get("name"),
        "brand": (pg.get("brand") or {}).get("name") if isinstance(pg.get("brand"), dict) else pg.get("brand"),
        "category": pg.get("category"),
        "composition": comp,
        "natural_pct": natural_pct,
        "primary_material": primary,
        "image": image,
        "colors": sorted(colors),
        "strikethrough_price": strike,
        "price_range": [min(pr), max(pr)] if pr else None,
        "sizes": sizes,
        "any_in_stock": any(s["in_stock"] for s in sizes),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = [extract(u) for u in sys.argv[1:]]
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
