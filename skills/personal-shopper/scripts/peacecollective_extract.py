#!/usr/bin/env python3
"""
Peace Collective (peace-collective.com) product extractor — VPS-side, NO bot wall.

Peace Collective is a Toronto DTC apparel brand (tees, crewnecks, hoodies, NFL/NBA
licensed) on Shopify. Cotton-heavy essentials line ("100% Cotton" heavyweight tees)
plus cotton/poly fleece — so the natural-fibre gate matters: READ THE %.

Which rung works (verified 2026-08-31):
  - Rung 2 (Shopify JSON), pure urllib from the VPS. NO Cloudflare/Akamai/PerimeterX.
  - price/compare/per-variant stock/image  ->  /products/<handle>.js  (prices in CENTS)
  - composition (fibre %)  ->  PDP HTML metafield bullet:  "• 60% Cotton, 40% Polyester"
    (a `multi_line_text_field` <div>; also mirrored in the product `tags[]` as e.g.
    "100% Cotton" when present, but tags are NOT reliable — licensed styles have none,
    so the HTML bullet is authoritative). Static HTML, no accordion click needed.

IMPORTANT: use the www. host. The apex peace-collective.com 301-redirects the .js/.json
to www., and a plain urllib GET without redirect-follow returns the redirect stub.

Usage:
    python3 peacecollective_extract.py <product-url-or-handle> [<url2> ...]
Example:
    python3 peacecollective_extract.py \
      https://www.peace-collective.com/products/it-s-not-me-...-caramel

Output per URL (JSON):
    {url, title, price, compare_at_price, on_sale, available, composition,
     natural_pct, image, sizes:[{size,price,available}], any_in_stock}
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# viscose/rayon/modal count as SYNTHETIC per the skill's fibre rule; lyocell/Tencel = natural.
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "lyocell", "tencel",
           "merino", "alpaca", "mohair", "jute", "ramie")
SYNTH = ("polyester", "nylon", "acrylic", "elastane", "spandex", "viscose", "rayon",
         "modal", "polyamide", "acetate", "polypropylene")


def _get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:  # urlopen follows 30x
        return r.read().decode("utf-8", "replace"), r.geturl()


def _handle(u):
    u = u.strip().rstrip("/")
    if "/products/" in u:
        return u.split("/products/", 1)[1].split("?")[0].split(".")[0]
    return u  # bare handle


def _natural_pct(comp):
    """comp like '60% Cotton, 40% Polyester' -> natural fibre % (int) or None."""
    if not comp:
        return None
    total = 0
    for pct, fib in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z ]+)", comp):
        f = fib.strip().lower()
        if any(n in f for n in NATURAL):
            total += int(pct)
    return total


def _composition(html):
    # The fibre metafield bullet: "• 60% Cotton, 40% Polyester" (may be "100% Cotton").
    m = re.search(
        r"[•\-\*]?\s*((?:\d{1,3}\s*%\s*[A-Za-z][A-Za-z ]*?)(?:,\s*\d{1,3}\s*%\s*[A-Za-z][A-Za-z ]*?)*)"
        r"\s*(?:<br|</|\n|•)",
        html)
    if m:
        cand = re.sub(r"\s+", " ", m.group(1)).strip(" ,")
        if "%" in cand:
            return cand
    return None


def extract(url):
    handle = _handle(url)
    base = "https://www.peace-collective.com/products/" + handle
    js, _ = _get(base + ".js", "application/json")
    d = json.loads(js)
    variants = d.get("variants", [])
    sizes = [{"size": v.get("title"), "price": v.get("price"),
              "available": v.get("available")} for v in variants]
    img = d.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img
    html, _ = _get(base, "text/html")
    comp = _composition(html)
    # tag fallback
    if not comp:
        m = re.search(r'"tags":\[([^\]]*)\]', js)
        if m:
            for t in re.findall(r'"([^"]*%[^"]*)"', m.group(1)):
                comp = t
                break
    return {
        "url": base,
        "title": d.get("title"),
        "price": d.get("price"),
        "compare_at_price": d.get("compare_at_price"),
        "on_sale": bool(d.get("compare_at_price")),
        "available": d.get("available"),
        "composition": comp,
        "natural_pct": _natural_pct(comp),
        "image": img,
        "sizes": sizes,
        "any_in_stock": any(v.get("available") for v in variants),
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
    print(json.dumps(out, indent=2))
