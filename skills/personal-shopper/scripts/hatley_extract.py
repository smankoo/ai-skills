#!/usr/bin/env python3
"""
hatley_extract.py — extract a Hatley (hatley.com) product for the personal-shopper skill.

Hatley is a Montreal-based Canadian brand: kids' pajamas/raincoats/tees AND adult
tees/rain jackets/sleepwear. It runs on **Shopify** with **NO bot wall** — plain
`urllib` from the VPS works (no exit node, no Mac delegation). Verified 2026-09-03.

Two fetches per product, both VPS-side:
  1. /products/<handle>.js   -> price/compare (CENTS), per-size stock, image, vendor/type
  2. /products/<handle>      -> PDP HTML; composition lives in a <strong>Materials</strong><br>...
     block (e.g. "95% Viscose From Bamboo, 5% Spandex"). NOT in the .js/.json.

Discovery: /search/suggest.json?q=<terms>&resources[type]=product&resources[limit]=N
  -> resources.results.products[] with handle + title.

USAGE:
  python3 hatley_extract.py <handle-or-full-product-url> [more...]
  python3 hatley_extract.py boys-trucks-bamboo-pajama-set
  python3 hatley_extract.py https://hatley.com/products/essential-crew-neck-tee-white

OUTPUT (JSON per product):
  {url, handle, title, vendor, type, price, compare_at_price, on_sale, currency,
   available, composition, natural_pct, image, sizes:[{size,price,available}],
   any_in_stock}

NOTES / FAILURE MODES:
  - Prices are in CENTS in .js (divide by 100). Currency is CAD (Canadian store).
  - compare_at_price present + > price => on sale (Hatley heavily discounts kids' PJs).
  - Composition: primary anchor is `<strong>Materials</strong><br>TEXT`. A secondary
    `<strong>Fabric & Stretch</strong>` line is marketing prose, not a fibre %.
  - Some products (licensed graphic tees, a few PJs) have NO structured Materials block
    and only vague prose ("Crafted from cotton and polyester") with no %. Those return
    composition=None / natural_pct=None -> treat as UNVERIFIED and exclude per the
    natural-fibre gate rather than guessing.
  - "Viscose From Bamboo" is regenerated cellulose => count as SYNTHETIC (like rayon/
    viscose) unless told otherwise. So a bamboo PJ at 95% viscose-from-bamboo is
    natural_pct 0, NOT 95 — the "bamboo" in the title lies. Cotton/wool/linen/silk/
    cashmere/lyocell(TENCEL)/hemp count as natural.
  - featured_image is protocol-relative (//cdn.shopify.com/...) -> prefix https:.
"""
import sys, json, re, html as htmlmod, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://hatley.com"

NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp",
           "lyocell", "tencel", "merino", "alpaca", "mohair", "jute", "ramie")
# viscose/rayon/modal/"viscose from bamboo"/bamboo(=viscose) => synthetic per skill rule


def _get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def natural_pct(comp):
    """Sum natural-fibre percentages from a composition string like '95% Viscose From Bamboo, 5% Spandex'."""
    if not comp:
        return None
    total = 0
    for m in re.finditer(r'(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /\-]*)', comp):
        pct = int(m.group(1))
        fibre = m.group(2).lower()
        # "viscose from bamboo" / bamboo / rayon / modal / polyester etc => synthetic
        if any(n in fibre for n in NATURAL) and "viscose" not in fibre and "bamboo" not in fibre:
            total += pct
    return total


def extract(handle):
    if handle.startswith("http"):
        handle = handle.rstrip("/").split("/products/")[-1].split("?")[0].split("#")[0]
    url = f"{BASE}/products/{handle}"
    out = {"url": url, "handle": handle}

    js = json.loads(_get(url + ".js", "application/json"))
    out["title"] = js.get("title")
    out["vendor"] = js.get("vendor")
    out["type"] = js.get("type")
    price = js.get("price")
    cmp_at = js.get("compare_at_price")
    out["price"] = round(price / 100, 2) if price is not None else None
    out["compare_at_price"] = round(cmp_at / 100, 2) if cmp_at else None
    out["on_sale"] = bool(cmp_at and price and cmp_at > price)
    out["currency"] = "CAD"
    out["available"] = js.get("available")
    img = js.get("featured_image")
    out["image"] = ("https:" + img) if img and img.startswith("//") else img
    sizes = []
    for v in js.get("variants", []):
        sizes.append({"size": v.get("title"),
                      "price": round(v["price"] / 100, 2) if v.get("price") is not None else None,
                      "available": v.get("available")})
    out["sizes"] = sizes
    out["any_in_stock"] = any(s["available"] for s in sizes)

    # composition from PDP HTML
    html = _get(url, "text/html")
    m = re.search(r'<strong>\s*Materials\s*</strong>\s*<br\s*/?>\s*([^<]{2,140})',
                  html, re.I)
    comp = htmlmod.unescape(m.group(1)).strip() if m else None
    out["composition"] = comp
    out["natural_pct"] = natural_pct(comp)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    results = [extract(a) for a in sys.argv[1:]]
    print(json.dumps(results if len(results) > 1 else results[0], indent=2))


if __name__ == "__main__":
    main()
