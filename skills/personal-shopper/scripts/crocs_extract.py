#!/usr/bin/env python3
"""crocs_extract.py (v2, 2026-10-08): Crocs Canada (crocs.ca) PDP extractor, pure urllib, VPS-side.

WHY v2: crocs.ca moved off SFCC/Demandware SiteGenesis onto a Next.js (App Router) headless
storefront (still SFCC data behind it). Old URLs `/<slug>/<id>,en_CA,pd.html` 301 to
`/p/<slug>/<id>.html`. The old `app.product.data.cache[...].masterData` block is GONE, so v1
returned only name/price from JSON-LD and silently dropped per-size stock.

Data now lives in two places in the server HTML (no bot wall, HTTP 200, ~1.3 MB):
  1. JSON-LD `<script id="ld-product">` -> name, image, offers.price (sale), priceCurrency CAD,
     availability.
  2. React Server Component flight payload: `self.__next_f.push([1,"..."])` string chunks. After
     un-escaping, the product object has `"variants":[{price, retailPrice, productId,
     variationValues:{size,color}, orderable, ats, isBisn, comingSoon}]` (one per colour x size)
     and `variationAttributes` (color/size value -> display name).

Usage:
    python3 crocs_extract.py "https://www.crocs.ca/p/classic-clog/10001.html"
    python3 crocs_extract.py "https://www.crocs.ca/classic-clog/10001,en_CA,pd.html"   # old URL ok
    python3 crocs_extract.py <url> --color 001         # restrict size table to one colour code
Output JSON: {url, style_id, name, price, regular_price, on_sale, currency, availability, image,
              colors:[{code,name}], sizes:[{size, in_stock, ats}] (aggregated over colours or for
              --color), any_in_stock, details[]}
Croslite foam -> no fibre % (natural-fibre gate N/A). Verified 2026-10-08 on 10001.
"""
import json, re, sys, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/141.0 Safari/537.36", "Accept-Language": "en-CA,en;q=0.9"}


def fetch(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45)
    return r.url, r.read().decode("utf-8", "replace")


def flight_text(html):
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html, re.S):
        try:
            out.append(json.loads('"' + m.group(1) + '"'))
        except Exception:
            pass
    return "".join(out)


def first_array(text, key, need=None):
    """First non-empty JSON array under "key":[...]; if need(val) given, first that satisfies it."""
    dec = json.JSONDecoder()
    for m in re.finditer(re.escape('"%s":[' % key), text):
        try:
            val, _ = dec.raw_decode(text, m.end() - 1)
            if val and (need is None or need(val)):
                return val
        except Exception:
            continue
    return []


def parse(url, html):
    out = {"url": url}
    m = re.search(r'<script type="application/ld\+json" id="ld-product">(.*?)</script>', html, re.S)
    if m:
        ld = json.loads(m.group(1))
        out["name"] = ld.get("name")
        out["style_id"] = ld.get("sku") or ld.get("productID")
        img = ld.get("image")
        out["image"] = img[0] if isinstance(img, list) and img else img
        of = ld.get("offers") or {}
        if isinstance(of, list):
            of = of[0] if of else {}
        out["price"] = of.get("price")
        out["currency"] = of.get("priceCurrency")
        out["availability"] = str(of.get("availability", "")).rsplit("/", 1)[-1]
        out["details"] = [s.strip() for s in re.split(r"(?<=\.)\s+", ld.get("description", "")) if s.strip()][:6]
    ft = flight_text(html)
    variants = first_array(ft, "variants")
    # image groups also carry a 1-colour variationAttributes; take the product-level one (has size)
    attrs = first_array(ft, "variationAttributes",
                        lambda v: any(isinstance(a, dict) and a.get("id") == "size" for a in v))
    names = {}
    for a in attrs:
        if isinstance(a, dict) and a.get("id") in ("color", "size"):
            for v in a.get("values") or []:
                names[(a["id"], v.get("value"))] = v.get("name") or v.get("value")
    out["colors"] = [{"code": c, "name": n} for (k, c), n in names.items() if k == "color"]
    want = None
    if "--color" in sys.argv:
        want = sys.argv[sys.argv.index("--color") + 1]
    by = {}
    rp = []
    for v in variants:
        vv = v.get("variationValues") or {}
        if want and vv.get("color") != want:
            continue
        sz = vv.get("size")
        if not sz:
            continue
        rec = by.setdefault(sz, {"size": sz, "in_stock": False, "ats": 0})
        if v.get("orderable") and (v.get("ats") or 0) > 0:
            rec["in_stock"] = True
        rec["ats"] += int(v.get("ats") or 0)
        if v.get("retailPrice"):
            rp.append(v["retailPrice"])
    out["sizes"] = list(by.values())
    out["n_variants"] = len(variants)
    out["any_in_stock"] = any(s["in_stock"] for s in out["sizes"])
    if rp:
        out["regular_price"] = max(rp)
        out["on_sale"] = bool(out.get("price") and out["price"] < max(rp))
    return out


def main():
    urls = [a for a in sys.argv[1:] if a.startswith("http")]
    res = []
    for u in urls:
        final, html = fetch(u)
        res.append(parse(final, html))
    print(json.dumps(res[0] if len(res) == 1 else res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
