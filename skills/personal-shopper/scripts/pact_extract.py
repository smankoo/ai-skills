#!/usr/bin/env python3
"""
Pact (wearpact.com) product extractor — personal-shopper skill.

Pact ("PACT" / Earth's Favorite) is a US organic-cotton DTC brand (Boulder, CO)
that ships to Canada. GOTS-certified organic cotton, Fair Trade factories —
a TOP natural-fibre source across women / men / kids / baby / home.

WHICH RUNG WORKS: a clean, undocumented public JSON API — rung 1 (no bot wall,
no headers, pure urllib from the VPS). The wearpact.com PDP is a jQuery SSR shell
whose price/stock/fabric all hydrate client-side from `https://api2.wearpact.io`
(the base URL is hard-coded in the site bundle static.wearpact.io/build/ui/bundle.*.js).

THE MONEY ENDPOINT:
    GET https://api2.wearpact.io/product/search?sku=<styleCode>
        [&country=CA]  [&isClearance=true]
  -> {total, records:[ ... one record PER SIZE (of the requested colour) ... ]}

  The <styleCode> is the LAST segment of a PDP URL, e.g.
    /women/apparel/all%20tops/soft-slub%20essential%20crewneck%20tee/wa1-w63-src
                                                                     ^^^^^^^^^^^ = wa1-w63-src
  Each record carries:
    title, color, colorCode, size, sizeCode, url,
    fabricContent + fiberContentDetailList  (authoritative composition),
    baseSkuPriceRange {msrp, sale} and priceList {WEB PRICE, WEB MSRP} (rate = dollars),
    inventoryList.'E-COMMERCE'.quantityAvailable  (per-size live stock),
    imageList[] (full + _thumb + swatch; ratio 33x40),
    status ('Current' / 'Closeout'), isClearance, isFinalSale, gotsCertified,
    fairTradeCertified, countryOfManufacture.

  Other useful endpoints seen in the bundle (same host, no headers):
    /product/page?path=<pdp-or-category-path>   -> category grid / page blocks
    /product/search?styleCode=<code>            -> (styleCode= matched 0; use sku=)
    /product/collection?search= , /product/outfit?search= , /product/sku

⚠️  CURRENCY: prices are ALWAYS **USD** (Pact is a US store; CA orders convert at
    checkout via global-e). `&country=CA` only FILTERS which sizes are shown for
    Canada — it does NOT convert the currency. Label the price USD in any cart.

NATURAL-FIBRE GATE: catalog is overwhelmingly organic cotton. Watch for:
    - "Cool Stretch" / leggings / movement = 95% organic cotton / 5% ELASTANE
      (elastane is synthetic; a 95/5 tee still clears a 70% gate at natural_pct 95).
    - Some knits/sweaters blend in recycled poly or modal — read the % from
      fiberContentDetailList, never trust the "organic cotton" in the name.

USAGE:
    python3 pact_extract.py wa1-w63-src [wa1-mln-blk ...]
    python3 pact_extract.py --country CA wa1-mln-blk
Prints one JSON object per style code.

Verified 2026-09-05 on wa1-w63-src (women's, 100% Organic Cotton, clearance) and
wa1-mln-blk (men's, 95% Organic Cotton/5% Elastane, current) — title, per-size
price/stock, composition, and image all matched the live site.
"""
import json
import sys
import urllib.request
import urllib.parse

API = "https://api2.wearpact.io/product/search"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "lyocell",
           "tencel", "merino", "alpaca", "mohair", "jute", "ramie")
# Everything else (elastane, spandex, polyester, nylon, acrylic, modal,
# viscose, rayon, recycled poly) counts as synthetic for the fibre gate.


def natural_pct(fibers):
    """Sum natural-fibre percentages from a list like ['95% Organic Cotton','5% Elastane']."""
    import re
    total = 0
    for f in fibers or []:
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%\s*(.+)", f)
        if not m:
            continue
        pct, name = float(m.group(1)), m.group(2).lower()
        if any(n in name for n in NATURAL):
            total += pct
    return round(total, 1)


def fetch(style, country=None, clearance=False):
    q = {"sku": style}
    if country:
        q["country"] = country
    if clearance:
        q["isClearance"] = "true"
    url = API + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def extract(style, country=None):
    d = fetch(style, country=country)
    recs = d.get("records", [])
    if not recs:
        return {"style": style, "found": False}
    r0 = recs[0]
    fibers = r0.get("fiberContentDetailList") or []
    rng = r0.get("baseSkuPriceRange", {})
    sale = (rng.get("sale") or {}).get("rate", {})
    msrp = (rng.get("msrp") or {}).get("rate", {})
    imgs = [i["url"] for i in r0.get("imageList", [])
            if not i.get("isThumbnail") and not i.get("isSwatch")]
    sizes = []
    for x in recs:
        inv = (x.get("inventoryList") or {}).get("E-COMMERCE", {})
        sizes.append({
            "size": x.get("size"),
            "sizeCode": x.get("sizeCode"),
            "qty_available": inv.get("quantityAvailable"),
            "in_stock": bool((inv.get("quantityAvailable") or 0) > 0),
            "externalId": x.get("externalId"),
        })
    return {
        "style": style,
        "found": True,
        "title": r0.get("title"),
        "color": r0.get("color"),
        "gender": r0.get("gender"),
        "category": r0.get("category"),
        "url": "https://wearpact.com" + (r0.get("url") or ""),
        "composition": r0.get("fabricContent"),
        "fibers": fibers,
        "natural_pct": natural_pct(fibers),
        "currency": "USD",                       # ALWAYS USD — see header note
        "sale_price": sale.get("min"),
        "msrp": msrp.get("min"),
        "on_sale": bool(sale.get("min") is not None and msrp.get("min")
                        and sale["min"] < msrp["min"]),
        "status": r0.get("status"),
        "is_clearance": r0.get("isClearance"),
        "is_final_sale": r0.get("isFinalSale"),
        "gots_certified": r0.get("gotsCertified"),
        "fair_trade": r0.get("fairTradeCertified"),
        "made_in": (r0.get("countryOfManufacture") or "").lstrip("_"),
        "image": imgs[0] if imgs else None,
        "sizes": sizes,
        "any_in_stock": any(s["in_stock"] for s in sizes),
    }


def main(argv):
    country = None
    styles = []
    it = iter(argv)
    for a in it:
        if a == "--country":
            country = next(it)
        else:
            styles.append(a)
    if not styles:
        print(__doc__)
        return 1
    for s in styles:
        try:
            print(json.dumps(extract(s, country=country), indent=1))
        except Exception as e:
            print(json.dumps({"style": s, "found": False, "error": str(e)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
