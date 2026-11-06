#!/usr/bin/env python3
"""
icebreaker_extract.py — extract product data from Icebreaker CA (na.icebreaker.com/en-ca).

Icebreaker is a Shopify store with a REQUIRED /en-ca/ locale prefix. From the VPS there is
NO bot wall — plain urllib works. Two fetches per product, both VPS-side:

  1. /en-ca/products/<handle>.js   -> price (CENTS), compare_at_price, top-level `available`,
     variants[] (option1=Color / option2=Size, per-variant `available` = live per-size stock),
     featured_image, title, tags, type.
  2. /en-ca/products/<handle>      -> PDP HTML; the AUTHORITATIVE composition is in
     `<strong>Fabric content</strong><p>NN% Fibre, ... exclusive of decoration</p>`.
     (body_html prose only says e.g. "100% merino" and OMITS blends entirely — do NOT trust it
     for the fibre gate; the Cool-Lite blends are 60% TENCEL Lyocell / 40% merino.)

CURRENCY TRAP: the `.js` price on /en-ca/ is market-localized to CAD (Tech Lite tee = C$105).
BUT the PDP JSON-LD `priceCurrency` is a stale template default of "USD" — IGNORE it. Trust the
`.js` price as CAD when fetched via the /en-ca/ path. (Same class of trap as Tilley / Naked & Famous.)

Icebreaker = 100% merino wool tees/base layers = a TOP natural-fibre source. Watch the Cool-Lite
"Cool-Lite" / "Sphere" blends: TENCEL Lyocell is plant-derived (count natural), but read the % —
a 60% Lyocell / 40% merino tee is 100% natural, whereas any recycled-poly variant is not.

Usage:
    python3 icebreaker_extract.py <handle-or-full-en-ca-product-URL> [...]
Example handle: merino-150-tech-lite-short-sleeve-t-shirt-ib0a56wl001

Output: one JSON object per product with
    {url, handle, title, type, price, compare_at_price, on_sale, currency, available,
     composition, natural_pct, image, colors[], sizes[],
     variants:[{color,size,price,available}], any_in_stock}
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://na.icebreaker.com/en-ca/products/"

# Fibres counted as natural (Lyocell/TENCEL/modal are plant-derived cellulosics -> natural here).
NATURAL = ("cotton", "wool", "merino", "linen", "silk", "cashmere", "hemp",
           "lyocell", "tencel", "modal", "alpaca", "mohair")


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def natural_pct(composition):
    """Sum the % of natural fibres in a 'NN% Fibre, MM% Fibre' string."""
    if not composition:
        return None
    total = 0
    for pct, name in re.findall(r'(\d{1,3})\s?%\s*([A-Za-z™\s\-]+)', composition):
        if any(n in name.lower() for n in NATURAL):
            total += int(pct)
    return total


def extract(handle_or_url):
    handle = handle_or_url.rstrip("/").split("/products/")[-1]
    handle = handle.split("?")[0].removesuffix(".js").removesuffix(".json")
    url = BASE + handle
    js = json.loads(_get(url + ".js"))

    variants = []
    colors, sizes = [], []
    for v in js.get("variants", []):
        color, size = v.get("option1"), v.get("option2")
        if color and color not in colors:
            colors.append(color)
        if size and size not in sizes:
            sizes.append(size)
        variants.append({
            "color": color, "size": size,
            "price": round(v["price"] / 100, 2),
            "available": v.get("available"),
        })

    # Composition: authoritative structured block in the PDP HTML.
    composition = None
    try:
        html = _get(url, html=True)
        m = re.search(r'<strong>\s*Fabric content\s*</strong>\s*<p>(.*?)</p>',
                      html, re.I | re.S)
        if m:
            composition = re.sub(r'\s+', ' ', m.group(1)).strip()
            composition = re.sub(r',?\s*exclusive of decoration\.?$', '', composition, flags=re.I)
    except Exception:
        pass
    if not composition:  # fallback: prose in body_html ("100% merino ...")
        desc = re.sub('<[^>]+>', ' ', js.get("description", ""))
        m = re.search(r'\b(\d{1,3}\s?%\s*merino[\w\s]*)', desc, re.I)
        if m:
            composition = m.group(1).strip()

    img = js.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    return {
        "url": url,
        "handle": handle,
        "title": js.get("title"),
        "type": js.get("type"),
        "price": round(js["price"] / 100, 2),
        "compare_at_price": round(js["compare_at_price"] / 100, 2) if js.get("compare_at_price") else None,
        "on_sale": bool(js.get("compare_at_price")),
        "currency": "CAD",  # /en-ca/ path is CAD; IGNORE JSON-LD's stale "USD"
        "available": js.get("available"),
        "composition": composition,
        "natural_pct": natural_pct(composition),
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
    out = [extract(a) for a in sys.argv[1:]]
    print(json.dumps(out if len(out) > 1 else out[0], indent=2, ensure_ascii=False))
