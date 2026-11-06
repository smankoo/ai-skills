#!/usr/bin/env python3
"""
Staples Canada (staples.ca) product extractor — pure urllib, runs on the VPS.

Staples.ca is a SHOPIFY store, so the standard `/products/<handle>.js` endpoint
returns full product JSON (title, price/compare_at in CENTS, per-variant stock,
image, and a very rich `tags[]` array carrying brand / model / UPC / rating /
category breadcrumb / spec attributes like `chair_seat_material_*`, `colour_*`).
The `.js` endpoint is NOT behind the Cloudflare wall that guards the bare PDP
and `.json` (both 403 "Just a moment..."). No exit node / Mac delegation needed.

Segment: Canada, general merchandise — office furniture, electronics, tech,
school/office supplies, some home. Confirmed in Sumeet's YNAB history. Mostly a
GIFT / home-office / gap-filler retailer, not apparel — so the natural-fibre
gate is usually N/A (chairs/electronics have no fibre %). Where an apparel-ish
item DOES have a material spec it surfaces in `tags` as `*_material_*` /
`*_upholstery_*` / `*_fabric_*` — this script collects those into `material`.

Discovery: `/search/suggest.json` is Cloudflare-blocked (returns empty). Find
candidate product URLs via `web_search "site:staples.ca products <keyword>"` —
result URLs are already the `/products/<handle>` shape; just append `.js`.

Usage:
    python3 staples_extract.py <product-url-or-handle> [<url2> ...]
    # handle = tail after /products/ ; a full PDP URL also works (we strip to handle)

Example output (one dict per URL):
    {
      "url": "https://www.staples.ca/products/2837129-en-staples-berwood-meshfabric-task-chair",
      "handle": "2837129-en-staples-berwood-meshfabric-task-chair",
      "title": "Staples Berwood Mesh/Fabric Task Chair",
      "brand": "staples",
      "price": 149.99, "compare_at_price": 199.99, "on_sale": true,
      "available": true, "price_varies": false,
      "material": ["Faux Leather"],          # from *_material_*/*_upholstery_*/*_fabric_* tags, [] if none
      "natural_pct": null,                    # only set if material carries a fibre %
      "model": "MB16ACV", "upc": "192876978498",
      "rating": 4.08, "n_reviews": 24,
      "categories": ["Furniture & Home", "Office Furniture", "Office Chairs"],
      "image": "https://cdn.shopify.com/.../..._1.jpg",
      "variants": [{"title","option1","option2","price","compare_at","available","sku"}],
      "any_in_stock": true
    }
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# fibres counted as natural for the natural-fibre gate (viscose/rayon = synthetic)
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "merino", "lambswool", "alpaca", "mohair", "jute", "ramie")


def _handle(u):
    u = u.strip()
    m = re.search(r"/products/([^/?#.]+)", u)
    h = m.group(1) if m else u
    return h.rstrip("/")


def _fetch_js(handle):
    url = f"https://www.staples.ca/products/{handle}.js"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _tag_val(tags, prefix):
    """Return the value after `prefix` for the first matching tag, else None."""
    for t in tags:
        if t.startswith(prefix):
            return t[len(prefix):]
    return None


def _tag_num(tags, prefix):
    """Tags like `AverageOverallRating:number:4.0785` -> 4.0785 (float)."""
    v = _tag_val(tags, prefix)
    if v is None:
        return None
    v = v.replace("number:", "")
    try:
        return float(v)
    except ValueError:
        return None


def _natural_pct(material_strings):
    """If any material string carries fibre percentages, compute natural share."""
    blob = " ".join(material_strings).lower()
    pairs = re.findall(r"(\d{1,3})\s*%\s*([a-z][a-z\- ]+)", blob)
    if not pairs:
        return None
    nat = 0
    for pct, fib in pairs:
        if any(n in fib for n in NATURAL):
            nat += int(pct)
    return nat


def extract(url):
    handle = _handle(url)
    d = _fetch_js(handle)
    tags = d.get("tags", []) or []

    # material / upholstery / fabric spec tags -> human values
    material = []
    for t in tags:
        tl = t.lower()
        if re.search(r"(_material_|_upholstery_|_fabric_|_fill_|_fibre_|_composition_)", tl):
            val = t.split(":", 1)[-1] if ":" in t else t.split("_")[-1]
            if val and val not in material:
                material.append(val)

    # category breadcrumb from bc_lN_name tags, in order
    cats = []
    for lvl in ("bc_l1_name:", "bc_l2_name:", "bc_l3_name:", "bc_l4_name:"):
        v = _tag_val(tags, lvl)
        if v:
            cats.append(v)

    price = d.get("price")
    cmp_at = d.get("compare_at_price")
    variants = []
    any_stock = False
    for v in d.get("variants", []):
        av = bool(v.get("available"))
        any_stock = any_stock or av
        variants.append({
            "title": v.get("title"),
            "option1": v.get("option1"),
            "option2": v.get("option2"),
            "price": (v.get("price") or 0) / 100.0,
            "compare_at": (v.get("compare_at_price") or 0) / 100.0 or None,
            "available": av,
            "sku": v.get("sku"),
        })

    fi = d.get("featured_image") or ""
    if fi.startswith("//"):
        fi = "https:" + fi

    rating = _tag_num(tags, "AverageOverallRating:")
    return {
        "url": f"https://www.staples.ca/products/{handle}",
        "handle": handle,
        "title": d.get("title"),
        "brand": _tag_val(tags, "brand:") or d.get("vendor"),
        "price": (price / 100.0) if price is not None else None,
        "compare_at_price": (cmp_at / 100.0) if cmp_at else None,
        "on_sale": bool(cmp_at and price and cmp_at > price),
        "available": bool(d.get("available")),
        "price_varies": bool(d.get("price_varies")),
        "material": material,
        "natural_pct": _natural_pct(material),
        "model": _tag_val(tags, "model_num:"),
        "upc": _tag_val(tags, "upc_code:"),
        "rating": round(rating, 2) if rating is not None else None,
        "n_reviews": int(_tag_num(tags, "TotalSubmittedReviews:") or 0),
        "categories": cats,
        "image": fi or None,
        "variants": variants,
        "any_in_stock": any_stock,
    }


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    out = []
    for u in argv[1:]:
        try:
            out.append(extract(u))
        except Exception as e:  # noqa: BLE001
            out.append({"url": u, "error": str(e)[:200]})
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
