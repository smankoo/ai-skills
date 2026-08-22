#!/usr/bin/env python3
"""
crocs_extract.py — extract name/price/sale/per-size stock/image from Crocs Canada (crocs.ca).

Crocs runs on Salesforce Commerce Cloud (Demandware). NO bot wall from the VPS — plain
urllib with a browser UA gets HTTP 200. Two data sources on the PDP HTML, both server-rendered:

  1. JSON-LD `Product` block  -> name, brand, image, aggregateRating, headline price/currency.
  2. A JS assignment `app.product.data.cache["<styleid>"].masterData = { ... }` -> the money block:
     - `variations`: one entry per colour×size SKU with {color, size, inStock, ATS (qty), UPC}.
     - `colors`: keyed by PRICE (supports sale) -> {isSale, price, regularPrice, formatted,
                 colors[], oosColors[]}.  Detects sale + which colours are sold out.
     - `skusBySize.oosSkus`: per-size list of OOS SKUs.
     - `tagMinPrice`, `isOOS`.

NOTE on composition: Crocs footwear is Croslite (EVA-type closed-cell foam), NOT a woven
fabric — the natural-fibre rule does NOT apply to it. The `Details` bullet list on the PDP
carries any bio-circular-material note (e.g. "25% bio-circular material"); this parser
surfaces the Details bullets as `details[]` so that can be shown, but there is no fibre %.

Usage:
    python3 crocs_extract.py "https://www.crocs.ca/classic-clog/10001,en_CA,pd.html"
    python3 crocs_extract.py <url1> <url2> ...

Output (per URL), JSON:
    {url, style_id, name, brand, image, price, currency, on_sale, regular_price,
     rating, rating_count, num_colors, oos_colors, sizes:[{size, in_stock, ats}],
     any_in_stock, details:[...]}

Product URL shape: https://www.crocs.ca/<slug>/<styleid>,en_CA,pd.html
Verified 2026-08-22 on 10001 (Classic Clog) and 206991 (Kids' Classic Clog).
"""
import sys, re, json, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(url, html):
    out = {"url": url}
    # style id from the URL: /<slug>/<styleid>,en_CA,pd.html
    m = re.search(r'/([0-9A-Za-z]+),[a-z]{2}_[A-Z]{2},pd\.html', url)
    out["style_id"] = m.group(1) if m else None

    # --- JSON-LD Product ---
    prod = None
    for b in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(b)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "Product":
            prod = j
            break
    if prod:
        out["name"] = prod.get("name")
        br = prod.get("brand")
        out["brand"] = br.get("name") if isinstance(br, dict) else br
        out["image"] = prod.get("image")
        offers = prod.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            out["price"] = offers.get("price")
            out["currency"] = offers.get("priceCurrency")
        ar = prod.get("aggregateRating") or {}
        out["rating"] = ar.get("ratingValue")
        out["rating_count"] = ar.get("ratingCount")

    # --- masterData JS block (per-size stock, sale, colours) ---
    m = re.search(r'\.masterData\s*=\s*(\{"variations":.*?\});?\s*</script>', html, re.S)
    if m:
        md = json.loads(m.group(1))
        out["is_oos"] = md.get("isOOS")
        out.setdefault("price", md.get("tagMinPrice"))
        # colours dict is keyed by price string; first entry is the live price tier
        colors = md.get("colors") or {}
        if isinstance(colors, dict) and colors:
            tier = next(iter(colors.values()))
            out["on_sale"] = bool(tier.get("isSale"))
            out["regular_price"] = tier.get("regularPrice")
            if tier.get("price") is not None:
                out["price"] = tier.get("price")
            out["num_colors"] = len(tier.get("colors") or [])
            out["oos_colors"] = tier.get("oosColors") or []
        # per-SIZE stock: aggregate across colours -> in stock if ANY colour has it
        by_size = {}
        for v in (md.get("variations") or {}).values():
            sz = v.get("size")
            if sz is None:
                continue
            rec = by_size.setdefault(sz, {"size": sz, "in_stock": False, "ats": 0})
            if v.get("inStock"):
                rec["in_stock"] = True
            rec["ats"] += int(v.get("ATS") or 0)
        out["sizes"] = list(by_size.values())
        out["any_in_stock"] = any(s["in_stock"] for s in out["sizes"])

    # --- Details bullets (bio-circular note lives here; no fibre %) ---
    details = []
    dm = re.search(r'Details:\*\*(.*?)(?:\n\n|SKU )', html, re.S)  # rendered-markdown case
    # HTML case: grab <li> items under the details container
    for li in re.findall(r'<li[^>]*>\s*([^<][^<]{3,120}?)\s*</li>', html):
        t = re.sub(r'<[^>]+>', '', li).strip()
        if t and ('material' in t.lower() or 'comfort' in t.lower()
                  or 'water' in t.lower() or 'light' in t.lower()):
            if t not in details:            # PDP renders the details block twice; dedup
                details.append(t)
    out["details"] = details[:8]
    return out


def main():
    urls = sys.argv[1:]
    if not urls:
        print(__doc__)
        sys.exit(1)
    res = [parse(u, fetch(u)) for u in urls]
    print(json.dumps(res if len(res) > 1 else res[0], indent=2))


if __name__ == "__main__":
    main()
