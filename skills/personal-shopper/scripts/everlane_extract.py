#!/usr/bin/env python3
"""
everlane_extract.py — Everlane (everlane.com) product extractor.

Everlane is a Shopify store (US-based; ships to Canada). NO bot wall from the VPS:
plain urllib works for both the Shopify `.js` endpoint (price/stock/variants/image)
and the PDP HTML (fibre composition). No exit node, no Mac delegation.

Natural-fibre relevance: Everlane is one of the strongest natural-fibre sources —
deep 100% organic-cotton tee/knit lines, 100% cashmere/merino sweaters, linen, and
denim. Cotton/cashmere/wool/linen lines routinely pass a high natural-fibre gate.
BUT: performance/tech lines (ReNew fleece, Performance Chino, activewear) are
predominantly recycled polyester/nylon — read the Materials block, don't trust the name.

⚠️ PRICES ARE IN USD. Everlane's Shopify runs `Shopify.currency.active == "USD"` and
JSON-LD `priceCurrency == "USD"` even on the CA-edge-served page. Convert to CAD for
Sumeet's cart (or note USD explicitly). The `.js` `price` is in CENTS (USD).

Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.
Verified 2026-08-29.

Usage:
    python3 everlane_extract.py <product-url-or-handle> [<url-or-handle> ...]
    # handle = the tail after /products/, e.g. mens-essential-organic-crew-uniform-white

Output (per product), JSON to stdout:
    {url, handle, title, type, vendor, price_usd, compare_at_usd, on_sale, available,
     composition, natural_pct, image, colors[], sizes[],
     variants:[{color,size,price_usd,compare_at_usd,available}], any_in_stock}

Find candidate handles via:
    web_search 'site:everlane.com/products <category> <keyword>'
    # or list the catalog: https://www.everlane.com/products.json?limit=250&page=N
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BASE = "https://www.everlane.com"

# Natural fibres for the gate. Viscose/rayon/modal count as SYNTHETIC (semi-synthetic)
# unless told otherwise. Recycled cotton/wool/cashmere still count as natural.
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "merino", "hemp",
           "lyocell", "tencel", "alpaca", "mohair", "ramie", "jute")


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _handle(s):
    s = s.strip()
    if "/products/" in s:
        s = s.split("/products/", 1)[1]
    return s.split("?")[0].split("#")[0].rstrip("/").removesuffix(".js").removesuffix(".json")


def natural_pct(comp):
    """Sum natural-fibre percentages from a composition string like
    '55% Linen, 45% Viscose' or '100% Organic Cotton'. Returns int or None."""
    if not comp:
        return None
    total = 0
    found = False
    for pct, name in re.findall(r'(\d{1,3})%\s*([A-Za-z][A-Za-z /()-]*)', comp):
        found = True
        if any(f in name.lower() for f in NATURAL):
            total += int(pct)
    return total if found else None


def composition(html):
    """Everlane PDP: static `ProductAccordion-Materials...>Materials:<ul><li>...</li></ul>`."""
    m = re.search(r'ProductAccordion-Materials[^>]*>\s*Materials:<ul>(.*?)</ul>', html, re.S)
    if not m:
        return None
    items = [re.sub(r'<[^>]+>', '', li).strip()
             for li in re.findall(r'<li>(.*?)</li>', m.group(1), re.S)]
    items = [i for i in items if i]
    return "; ".join(items) if items else None


def extract(url_or_handle):
    h = _handle(url_or_handle)
    url = f"{BASE}/products/{h}"
    js = json.loads(_get(url + ".js"))
    html = _get(url, html=True)

    comp = composition(html)
    variants = []
    colors, sizes = [], []
    for v in js.get("variants", []):
        # Everlane variant options: usually option1=size (tops) or option1=waist/option2=inseam
        # (bottoms). Color is usually fixed per handle (one handle per colourway).
        color = js.get("title", "").split("|")[-1].strip() if "|" in js.get("title", "") else None
        size = v.get("title")
        variants.append({
            "color": color, "size": size,
            "price_usd": round(v.get("price", 0) / 100, 2),
            "compare_at_usd": round(v["compare_at_price"] / 100, 2) if v.get("compare_at_price") else None,
            "available": v.get("available"),
        })
        if size and size not in sizes:
            sizes.append(size)
        if color and color not in colors:
            colors.append(color)

    img = js.get("featured_image")
    if img and img.startswith("//"):
        img = "https:" + img

    return {
        "url": url,
        "handle": h,
        "title": js.get("title"),
        "type": js.get("type"),
        "vendor": js.get("vendor"),
        "price_usd": round(js.get("price", 0) / 100, 2),
        "compare_at_usd": round(js["compare_at_price"] / 100, 2) if js.get("compare_at_price") else None,
        "on_sale": bool(js.get("compare_at_price")),
        "available": js.get("available"),
        "composition": comp,
        "natural_pct": natural_pct(comp),
        "image": img,
        "colors": colors,
        "sizes": sizes,
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for arg in sys.argv[1:]:
        try:
            out.append(extract(arg))
        except Exception as e:
            out.append({"url": arg, "error": f"{type(e).__name__}: {e}"})
    print(json.dumps(out, indent=2, ensure_ascii=False))
