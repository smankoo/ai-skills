#!/usr/bin/env python3
"""
littleandlively_extract.py — Little & Lively (littleandlively.com)

Canadian (made-in-BC) kids + baby + women/men "bamboo" apparel DTC. Standard
Shopify store, NO bot wall — a single `/products/<handle>.js` call from the VPS
returns EVERYTHING the personal-shopper skill needs:
  * price / compare_at_price (CENTS, CAD — store default is CAD, no currency field)
  * per-variant (per-size) `available` boolean  -> live stock
  * featured_image (protocol-relative //cdn.shopify.com -> prefix https:)
  * fibre composition embedded in the `description` HTML as a
    "Fabric - 66% Rayon from Bamboo, 28% Cotton, 6% Spandex" <li>.

⚠️ NATURAL-FIBRE GATE — this whole store FAILS a 70% gate.
Little & Lively's ENTIRE catalog (as of 2026-09-07) is one "bamboo" fabric:
**66% Rayon from Bamboo, 28% Cotton, 6% Spandex**. "Rayon from Bamboo" is
viscose = SEMI-SYNTHETIC (count as synthetic unless told otherwise), so
natural_pct = 28% (cotton only). Despite the eco/"bamboo" branding, every piece
is well below 70% natural fibre. Report it and exclude — don't be fooled by the
sustainable marketing. (If they ever add a true cotton line, this parser reads
whatever the `Fabric -` line says.)

Run:
  UA="Mozilla/5.0 ..."; curl -s -A "$UA" \
    "https://littleandlively.com/products/<handle>.js" -o p.js
  python3 littleandlively_extract.py p.js
  # or pass a URL/handle and it fetches:
  python3 littleandlively_extract.py https://littleandlively.com/products/<handle>

Output (one JSON object per input):
  {handle, url, title, price, compare_at_price, on_sale, available, currency,
   image, composition, natural_pct, sizes[], variants[{size,price,available,sku}],
   any_in_stock}

Discover handles (no bot wall):
  curl -s "https://littleandlively.com/products.json?limit=250"          -> products[].handle
  curl -s "https://littleandlively.com/collections/<c>/products.json"
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://littleandlively.com"

# fibres to count as NATURAL. Rayon/Bamboo/Viscose/Modal are semi-synthetic ->
# NOT counted (viscose rule). Spandex/Polyester/Nylon/Elastane are synthetic.
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "merino", "hemp",
           "lyocell", "tencel")
FIB_RE = re.compile(r'(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /®™]*)')


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_composition(description_html):
    """Return (composition_string, natural_pct) from the 'Fabric -' <li>."""
    if not description_html:
        return None, None
    # find the fabric line: "Fabric - 66% Rayon from Bamboo, 28% Cotton, 6% Spandex"
    m = re.search(r'Fabric\s*[-:]\s*([^<]+)', description_html, re.I)
    if not m:
        # fallback: any line containing a % + a fibre word
        m = re.search(r'([^<>]*\d{1,3}\s*%[^<>]*(?:Cotton|Bamboo|Rayon|Wool|Linen)[^<>]*)',
                      description_html, re.I)
        if not m:
            return None, None
    comp = m.group(1).strip().rstrip(".")
    natural = 0
    for pct, fib in FIB_RE.findall(comp):
        fl = fib.strip().lower()
        # "rayon from bamboo" / "bamboo" / "viscose" / "modal" -> semi-synthetic, skip
        if any(n in fl for n in NATURAL) and "bamboo" not in fl and "rayon" not in fl:
            natural += int(pct)
    return comp, natural


def extract(handle_or_url):
    if handle_or_url.startswith("http"):
        url = handle_or_url.split("?")[0].rstrip("/")
        if url.endswith(".js"):
            url = url[:-3]
        handle = url.rsplit("/products/", 1)[-1]
    else:
        handle = handle_or_url
        url = f"{BASE}/products/{handle}"
    js = json.loads(fetch(f"{BASE}/products/{handle}.js"))
    comp, natural = parse_composition(js.get("description", ""))
    img = js.get("featured_image")
    if img and img.startswith("//"):
        img = "https:" + img
    variants = [{"size": v.get("option1"), "price": v["price"] / 100.0,
                 "available": v["available"], "sku": v.get("sku")}
                for v in js.get("variants", [])]
    cap = js.get("compare_at_price") or 0
    return {
        "handle": handle,
        "url": url,
        "title": js.get("title"),
        "price": js.get("price", 0) / 100.0,
        "compare_at_price": (cap / 100.0) if cap else None,
        "on_sale": bool(cap and cap > js.get("price", 0)),
        "available": js.get("available"),
        "currency": "CAD",           # store default; .js has no currency field
        "image": img,
        "composition": comp,
        "natural_pct": natural,      # 28 for the bamboo line -> FAILS a 70% gate
        "sizes": [v.get("option1") for v in js.get("variants", [])],
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    out = []
    for a in args:
        if a.endswith(".js") and "/" not in a.replace("\\", "/").rstrip("/"):
            # local file
            js = json.loads(open(a).read())
            comp, natural = parse_composition(js.get("description", ""))
            img = js.get("featured_image")
            if img and img.startswith("//"):
                img = "https:" + img
            out.append({"handle": js.get("handle"), "title": js.get("title"),
                        "price": js.get("price", 0) / 100.0, "composition": comp,
                        "natural_pct": natural, "image": img})
        else:
            try:
                out.append(extract(a))
            except Exception as e:
                out.append({"input": a, "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))
