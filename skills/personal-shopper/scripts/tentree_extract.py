#!/usr/bin/env python3
"""
tentree_extract.py — extract product data from tentree.ca (Canadian sustainable apparel).

WHY: tentree is a top natural-fibre source (organic cotton, hemp, TENCEL/lyocell) that
sells men's/women's/kids' apparel with Canadian delivery. It's a Shopify store with NO
bot wall from the VPS — plain urllib works (no exit node, no Mac delegation).

METHOD (two VPS-side fetches per product):
  1. Shopify `/products/<handle>.js`  -> price/compare_at (CENTS), per-variant colour/size
     + a real `available` boolean (per-size stock), sku, featured_image.
  2. PDP HTML `/products/<handle>`     -> the authoritative composition, in a single
     `fabric-composition="..."` HTML attribute. The `.js`/`.json` `description` only
     sometimes carries the fibre %, so ALWAYS read the attribute for the natural-fibre gate.

NOTE: TENCEL/lyocell is plant-derived — counted NATURAL here (per skill rule). Recycled
polyester, nylon, elastane/spandex, acrylic, viscose/rayon, modal = SYNTHETIC. tentree's
"TreeBlend" tri-blend tees are ~45% recycled polyester -> FAIL a 70% natural gate; its plain
organic-cotton tees are 100% cotton -> PASS. Read the % — the name ("cotton") lies about blends.

USAGE:
  python3 tentree_extract.py https://www.tentree.ca/products/<handle> [<handle-or-url> ...]

OUTPUT (per URL), JSON to stdout:
  {url, handle, title, vendor, type, price, compare_at_price, on_sale, available,
   composition, natural_pct, image, colors[], sizes[],
   variants:[{color,size,price,compare_at,available,sku}], any_in_stock}
"""
import sys, json, re, html, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# fibres counted as natural (lyocell/TENCEL is plant-derived -> natural per skill rule)
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp",
           "lyocell", "tencel", "merino", "jute", "ramie")


def _get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _handle(u):
    u = u.strip().rstrip("/")
    if u.startswith("http"):
        u = re.sub(r"[?#].*$", "", u)
        return u.rsplit("/products/", 1)[-1]
    return u


def _composition(pdp_html):
    """Read the authoritative `fabric-composition="..."` attribute, strip tags/entities."""
    m = re.search(r'fabric-composition="([^"]*)"', pdp_html)
    if not m:
        return None
    raw = html.unescape(m.group(1))
    raw = re.sub(r"<[^>]+>", "", raw)          # drop embedded <a>/<u> tags
    raw = raw.split(":", 1)[-1] if ":" in raw and "%" in raw.split(":", 1)[-1] else raw
    return re.sub(r"\s+", " ", raw).strip(" :")


def _natural_pct(comp):
    if not comp:
        return None
    total = 0
    for pct, fibre in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /™\-]*)", comp):
        if any(n in fibre.lower() for n in NATURAL):
            total += int(pct)
    return total


def extract(url_or_handle):
    handle = _handle(url_or_handle)
    base = f"https://www.tentree.ca/products/{handle}"
    d = json.loads(_get(base + ".js", "application/json"))
    pdp = _get(base, "text/html")
    comp = _composition(pdp)

    variants = [{
        "color": v.get("option1"), "size": v.get("option2"),
        "price": v["price"] / 100.0,
        "compare_at": (v.get("compare_at_price") or 0) / 100.0 or None,
        "available": v["available"], "sku": v.get("sku"),
    } for v in d.get("variants", [])]

    img = d.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    return {
        "url": base,
        "handle": handle,
        "title": d.get("title"),
        "vendor": d.get("vendor"),
        "type": d.get("type"),
        "price": d["price"] / 100.0,
        "compare_at_price": (d.get("compare_at_price") or 0) / 100.0 or None,
        "on_sale": bool(d.get("compare_at_price") and d["compare_at_price"] > d["price"]),
        "available": d.get("available"),
        "composition": comp,
        "natural_pct": _natural_pct(comp),
        "image": img,
        "colors": sorted({v["color"] for v in variants if v["color"]}),
        "sizes": sorted({v["size"] for v in variants if v["size"]}),
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for u in sys.argv[1:]:
        try:
            out.append(extract(u))
        except Exception as e:
            out.append({"url": u, "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))
