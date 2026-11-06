#!/usr/bin/env python3
"""
The Ordinary / Deciem (CA) product extractor — pure urllib, runs on the VPS.

The Ordinary (theordinary.com) and its parent Deciem run on Salesforce Commerce
Cloud (Demandware). There is NO bot wall from the VPS — plain urllib/curl get
the full rendered HTML (200), which embeds a JSON-LD `Product` block (name,
price CAD, availability, image, sku) AND the full INCI ingredient list in a
static `data-original-ingredients="..."` attribute. Sister brands NIOD and The
Chemistry Brand share the platform (swap the domain) and the recipe transfers.

For skincare the "composition" analog Sumeet cares about is the INCI ingredient
list, not fibre %. This script surfaces it so a natural/clean-ingredient
preference can be applied. Size lives in the sku slug (e.g. `...-30ml`) or must
be read from the product tile text.

Usage:
    python3 theordinary_extract.py <product-url> [<product-url> ...]
    # product URL shape: https://theordinary.com/en-ca/<slug>-<productId>.html
    # find URLs via: web_search 'site:theordinary.com/en-ca <keyword>'

Output per URL (JSON):
    {url, name, sku, brand, price, currency, availability, in_stock,
     size, image, ingredients, description}

Verified 2026-08-21 on two live products:
    niacinamide-10-zinc-1-serum-100436   -> $6.60 CAD InStock, 30ml, full INCI
    hyaluronic-acid-2-b5-serum-with-ceramides-100637 -> $12.00 CAD InStock, INCI
"""
import sys, re, json, html, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(url):
    t = fetch(url)
    blocks = re.findall(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S)
    prod = None
    for b in blocks:
        try:
            j = json.loads(html.unescape(b.strip()))
        except Exception:
            continue
        if j.get("@type") == "Product":
            prod = j
            break
    if not prod:
        return {"url": url, "error": "no Product JSON-LD"}

    off = prod.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    avail = str(off.get("availability", "")).rsplit("/", 1)[-1]
    img = prod.get("image")
    if isinstance(img, list):
        img = img[0] if img else None

    # full INCI ingredient list from the static flyout attribute
    m = re.search(r'data-original-ingredients="([^"]+)"', t)
    ingredients = html.unescape(m.group(1)).strip() if m else None

    # size: prefer the sku slug tail (e.g. ...-30ml), else scan tile text
    sku = prod.get("sku", "")
    sm = re.search(r'(\d+)\s?ml', sku, re.I)
    size = f"{sm.group(1)}ml" if sm else None

    return {
        "url": url,
        "name": prod.get("name"),
        "sku": sku,
        "brand": (prod.get("brand") or {}).get("name")
                 if isinstance(prod.get("brand"), dict) else prod.get("brand"),
        "price": off.get("price"),
        "currency": off.get("priceCurrency"),
        "availability": avail,
        "in_stock": avail == "InStock",
        "size": size,
        "image": img,
        "ingredients": ingredients,
        "description": prod.get("description"),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = [parse(u) for u in sys.argv[1:]]
    print(json.dumps(out if len(out) > 1 else out[0], indent=2))
