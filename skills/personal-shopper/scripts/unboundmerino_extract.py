#!/usr/bin/env python3
"""
unboundmerino_extract.py — Unbound Merino (unboundmerino.com) product extractor.

Canada-shipping Shopify DTC. Merino-wool specialist: 100% merino tees/base layers,
merino/linen blends, merino/nylon socks — a top natural-fibre source (adult men's +
women's; travel/everyday). NO bot wall — pure urllib from the VPS.

WHICH RUNG WORKED: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.
  - /products/<handle>.js?currency=CAD  -> price/compare (CENTS, CAD), per-variant
    stock (option1=colour / option2=size), featured_image, all VPS-side.
    IMPORTANT: the store DEFAULTS TO USD. You MUST append ?currency=CAD to the .js
    call or you get USD prices (Shopify.currency.active == "USD").
  - Composition is NOT in the .js/.json. It lives in the STATIC PDP HTML as the first
    <li> under <ul class="product-tab__details-list">, e.g.
        <li>75% Merino Wool, 25% Linen</li>
        <li>100% Merino Wool, Jersey</li>
    (curl gets it — no accordion click needed).

USAGE:
    python3 unboundmerino_extract.py <product-url-or-handle> [<url2> ...]
    # e.g.
    python3 unboundmerino_extract.py womens-merino-linen-shirt \
        https://unboundmerino.com/products/mens-merino-linen-tropical-shirt

OUTPUT (per URL): JSON dict
    {url, handle, title, price_cad, compare_at_cad, on_sale, available, composition,
     natural_pct, image, colors[], sizes[], variants:[{color,size,price_cad,available}],
     any_in_stock}

NOTE: natural_pct sums merino/wool/linen/cotton/silk/cashmere/lyocell/tencel as
natural; nylon/elastane/polyester/spandex/acrylic/viscose/rayon as synthetic.
Merino "Jersey"/knit descriptors carry no % and are ignored.
Verified 2026-09-02 on 3 live products (75/25 merino-linen shirt CAD $280;
merino-linen tropical shirt CAD $266; 100% merino sleep crew).
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://unboundmerino.com"

NATURAL = ("merino", "wool", "linen", "cotton", "silk", "cashmere",
           "lyocell", "tencel", "alpaca", "mohair", "hemp")


def _get(url, html=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html" if html else "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def handle_of(u):
    u = u.strip()
    if "/products/" in u:
        u = u.split("/products/", 1)[1]
    return u.split("?")[0].split("#")[0].rstrip("/").replace(".js", "").replace(".json", "")


def natural_pct(composition):
    """Sum natural-fibre percentages from a 'NN% Fibre, NN% Fibre' string."""
    if not composition:
        return None
    total = 0
    for pct, fibre in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z ]+)", composition):
        if any(nat in fibre.lower() for nat in NATURAL):
            total += int(pct)
    return total if re.search(r"\d+\s*%", composition) else None


def composition_of(html):
    """First <li> under ul.product-tab__details-list that carries a fibre %."""
    flat = re.sub(r"\s+", " ", html)
    m = re.search(r'product-tab__details-list"\s*>(.*?)</ul>', flat)
    scope = m.group(1) if m else flat
    for li in re.findall(r"<li[^>]*>([^<]+)</li>", scope):
        if re.search(r"\d+\s*%", li) and any(n in li.lower() for n in NATURAL):
            return li.strip()
    return None


def extract(url_or_handle):
    h = handle_of(url_or_handle)
    js = json.loads(_get(f"{BASE}/products/{h}.js?currency=CAD"))
    pdp = _get(f"{BASE}/products/{h}", html=True)
    comp = composition_of(pdp)

    variants = []
    colors, sizes = [], []
    for v in js.get("variants", []):
        color = v.get("option1")
        size = v.get("option2")
        if color and color not in colors:
            colors.append(color)
        if size and size not in sizes:
            sizes.append(size)
        variants.append({
            "color": color, "size": size,
            "price_cad": round(v["price"] / 100, 2),
            "available": v["available"],
        })

    img = js.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img

    return {
        "url": f"{BASE}/products/{h}",
        "handle": h,
        "title": js.get("title"),
        "price_cad": round(js["price"] / 100, 2),
        "compare_at_cad": round(js["compare_at_price"] / 100, 2) if js.get("compare_at_price") else None,
        "on_sale": bool(js.get("compare_at_price") and js["compare_at_price"] > js["price"]),
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
    for arg in sys.argv[1:]:
        try:
            print(json.dumps(extract(arg), indent=2, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"url": arg, "error": str(e)}))
