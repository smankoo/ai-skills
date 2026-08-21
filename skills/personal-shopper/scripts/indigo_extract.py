#!/usr/bin/env python3
"""
Indigo / Chapters (indigo.ca) product extractor — books, gifts & home ("GM").

Indigo migrated chapters.indigo.ca -> www.indigo.ca and the new site is a
**Shopify store** with NO bot wall from the VPS (plain urllib works; no exit
node, no Mac delegation). Old `chapters.indigo.ca/.../<isbn>-item.html` URLs
301 -> `indigo.ca/search?q=<isbn>`; current product URLs are `/products/<handle>`.

Two data sources, both open VPS-side:
  1. `/products/<handle>.js`   -> Shopify product JSON: price/compare_at (CENTS),
     top-level `available`, `type` (Book|GM), `vendor`, `tags`, `featured_image`,
     and `variants[]` — one per FORMAT for books (Hardcover / Paperback /
     Audiobook / Kobo eBook), each with `price` (cents) + `available` boolean =
     per-format price & stock directly.
  2. PDP HTML `/products/<handle>`  -> two `application/ld+json` blocks; block[1]
     is a **ProductGroup** whose `hasVariant[]` carries, per variant:
     `sku`/`gtin13` (= the ISBN13 for books), `brand.name` (= publisher),
     `offers.price` (DOLLARS), `offers.availability`, and top-level
     `aggregateRating` ({ratingValue, ratingCount}). The **author** is not in
     JSON-LD — it's in the `<title>`: "<Name> by <Author>, (<Format>) | Indigo".

This script uses the `.js` for the buyable facts (fast, one request) and
optionally the PDP HTML for ISBN/publisher/author/rating (`--full`).

Fibre composition is N/A here (books/gifts) — the natural-fibre gate doesn't
apply. Indigo is the "books & gifts" store for the gift track, not apparel.

Run:
    python3 indigo_extract.py atomic-habits                 # handle
    python3 indigo_extract.py https://www.indigo.ca/products/atomic-habits --full
    python3 indigo_extract.py atomic-habits floral-decal-candle-11oz --full

Output (per product), JSON:
    {handle, url, title, type, vendor, price, compare_at_price, on_sale,
     available, image, formats:[{format, price, available}],
     isbn, publisher, author, rating, rating_count}   # last 5 only with --full
"""
import json, re, sys, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://www.indigo.ca"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def handle_of(arg):
    """Accept a bare handle or any /products/<handle>[?...] URL."""
    m = re.search(r"/products/([^/?#]+)", arg)
    return m.group(1) if m else arg.strip().strip("/")


def cents(v):
    return round(v / 100.0, 2) if isinstance(v, (int, float)) else None


def extract(arg, full=False):
    h = handle_of(arg)
    j = json.loads(_get(f"{BASE}/products/{h}.js"))
    out = {
        "handle": h,
        "url": f"{BASE}/products/{h}",
        "title": j.get("title"),
        "type": j.get("type"),                 # "Book" | "GM"
        "vendor": j.get("vendor"),             # publisher (books) / brand (GM)
        "price": cents(j.get("price")),        # lowest live price, dollars
        "compare_at_price": cents(j.get("compare_at_price")) or None,
        "available": j.get("available"),
        "image": ("https:" + j["featured_image"]) if str(j.get("featured_image", "")).startswith("//")
                  else j.get("featured_image"),
        "formats": [{"format": v.get("title"),
                     "price": cents(v.get("price")),
                     "available": v.get("available")}
                    for v in j.get("variants", [])],
    }
    out["on_sale"] = bool(out["compare_at_price"] and out["price"]
                          and out["compare_at_price"] > out["price"])
    if full:
        try:
            html = _get(out["url"])
            # author from <title>: "<name> by <Author>, (<Format>) | Indigo"
            mt = re.search(r"<title>(.*?)</title>", html, re.S)
            if mt:
                ma = re.search(r"\bby\s+(.+?),\s*\(", mt.group(1))
                out["author"] = ma.group(1).strip() if ma else None
            blocks = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                                html, re.S)
            pg = None
            for b in blocks:
                try:
                    d = json.loads(b)
                except Exception:
                    continue
                if d.get("@type") == "ProductGroup":
                    pg = d
                    break
            if pg:
                var = (pg.get("hasVariant") or [{}])[0]
                out["isbn"] = var.get("gtin13") or var.get("sku")
                br = var.get("brand")
                out["publisher"] = br.get("name") if isinstance(br, dict) else br
                agg = pg.get("aggregateRating") or {}
                out["rating"] = agg.get("ratingValue")
                out["rating_count"] = agg.get("ratingCount")
        except Exception as e:
            out["_full_error"] = str(e)[:80]
    return out


def main():
    args = [a for a in sys.argv[1:] if a != "--full"]
    full = "--full" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    res = [extract(a, full=full) for a in args]
    print(json.dumps(res if len(res) > 1 else res[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
