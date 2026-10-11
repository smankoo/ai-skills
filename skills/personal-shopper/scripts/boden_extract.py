#!/usr/bin/env python3
"""Boden (us.boden.com) product extractor — personal-shopper skill.

Boden is a headless Shopify store (US storefront `us.boden.com`, ships to Canada).
Everything runs from the VPS with a plain `urllib` GET — NO bot wall, no Mac, no
exit node. Two fetches per product:

  1. /products/<handle>.js   -> price (CENTS, **USD**), per-size stock (variants[].available),
                                featured_image, colours/sizes. Composition is NOT here.
  2. /products/<handle>      -> PDP HTML; composition lives under the "Composition"
                                <h3> inside <ul class="product-bullet-groups__list">
                                as <li>Main: 100% cotton</li> etc.

⚠️  PRICES ARE USD. us.boden.com has no CAD storefront; `?currency=CAD` is IGNORED
    (still returns USD cents) and there is no ca.boden.com. Boden ships to Canada
    and converts at Global-e checkout. Treat the number as USD and say so.

⚠️  The public `/products.json` feed lists STALE handles that 404 on the storefront.
    Discover LIVE handles from the sitemap instead:
      https://us.boden.com/sitemap.xml -> sitemap_products_N.xml?from=..&to=..
    (the from/to query params are REQUIRED — bare sitemap_products_N.xml → HTTP 400).

⚠️  Composition can have multiple parts (Main / Rib / Lining). The parser reports the
    WORST-CASE (minimum) natural % across parts, so a mixed garment can't sneak past a
    fibre gate on its Main-fabric line alone.

Usage:
    python3 boden_extract.py <handle-or-full-url> [<handle-or-full-url> ...]

Example handle: boys-cosy-mid-weight-t-shirt-blue-aura-sweet-cherry-b3091bbl
Output: one JSON object per line (JSONL).
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")
BASE = "https://us.boden.com"

# fibres counted as natural (lyocell/Tencel/modal are plant-derived -> natural;
# viscose/rayon/bamboo are semi-synthetic -> NOT counted, per the skill's viscose rule).
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "merino", "mohair", "alpaca", "modal")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html,application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def _handle(arg):
    if arg.startswith("http"):
        m = re.search(r"/products/([^/?#.]+)", arg)
        return m.group(1) if m else arg
    return arg.strip()


def _natural_pct(parts):
    """parts = list of 'component: NN% fibre, ...' strings. Return worst-case natural %."""
    worst = None
    detail = []
    for part in parts:
        toks = re.findall(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /-]*?)(?=[,;.]|\s*\d|$)", part)
        if not toks:
            continue
        nat = 0
        for pct, fib in toks:
            if any(n in fib.lower() for n in NATURAL):
                nat += int(pct)
        detail.append({"part": part, "natural": nat})
        worst = nat if worst is None else min(worst, nat)
    return worst, detail


def extract(handle):
    handle = _handle(handle)
    out = {"handle": handle, "url": f"{BASE}/products/{handle}"}
    # 1. .js — price/stock/image
    js = json.loads(_get(f"{BASE}/products/{handle}.js"))
    out["title"] = js.get("title")
    out["price_usd"] = round(js.get("price", 0) / 100, 2)          # CENTS -> dollars, USD
    cmp_ = js.get("compare_at_price") or 0
    out["compare_at_usd"] = round(cmp_ / 100, 2) if cmp_ else None
    out["on_sale"] = bool(cmp_ and cmp_ > js.get("price", 0))
    out["currency"] = "USD"                                        # store is USD-locked
    out["available"] = js.get("available")
    img = js.get("featured_image") or ""
    out["image"] = ("https:" + img) if img.startswith("//") else img
    variants = js.get("variants", [])
    # Boden uses option1=Size for single-colour handles; option2 sometimes size.
    def size_of(v):
        return v.get("option2") or v.get("option1")
    out["sizes"] = sorted({size_of(v) for v in variants if size_of(v)})
    out["variants"] = [{"size": size_of(v), "price_usd": round(v.get("price", 0) / 100, 2),
                        "available": v.get("available"), "sku": v.get("sku")}
                       for v in variants]
    out["any_in_stock"] = any(v.get("available") for v in variants)
    # 2. PDP HTML — composition
    html = _get(f"{BASE}/products/{handle}")
    comp_parts = []
    m = re.search(r"Composition</h3>\s*<ul[^>]*>(.*?)</ul>", html, re.S)
    if m:
        comp_parts = [re.sub(r"<[^>]+>", "", li).strip()
                      for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S)]
    out["composition"] = comp_parts
    nat, detail = _natural_pct(comp_parts)
    out["natural_pct_worst"] = nat
    out["composition_detail"] = detail
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for arg in sys.argv[1:]:
        try:
            print(json.dumps(extract(arg), ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"handle": _handle(arg), "error": str(e)}))
