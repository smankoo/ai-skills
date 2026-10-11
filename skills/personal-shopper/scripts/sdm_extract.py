#!/usr/bin/env python3
"""
sdm_extract.py — Shoppers Drug Mart (CA) product data from the VPS, no browser.

The www/api.shoppersdrugmart.ca hosts are Akamai-403 from the VPS, but the Loblaw
"beauty" BFF host the site itself calls is NOT walled. It just needs the public web
x-apikey that ships in the site's _app JS bundle (NEXT_PUBLIC_BFF_API_KEY):

  BASE = https://prod-sdm-bff.api.loblaw.digital/beauty/v2/shoppersdrugmart
  GET  /product/variantProduct/<EAN>/details?province=ON   -> name, price, sale, stock, size, images, ingredients
  GET  /product/baseProduct/BB_<EAN>/details              -> variantsSummary (per-size OOS), promotions, breadcrumbs
  GET  /product/<EAN>/fulfillment-options?storeId=&postalCode=L7M0K5 -> ship status + ETA

Headers: x-apikey, x-application-type: Web, accept: application/json, browser UA.

SEARCH is not exposed as a GET API (server-side rendered). Do search on the iMac with
sdm_extract.js (reads __NEXT_DATA__ productTiles) and then feed codes/URLs here.

USAGE
  python3 sdm_extract.py <EAN | BB_<EAN> | product URL> [...]  [--postal L7M0K5]
OUTPUT: one JSON object per product on stdout.

If the key rotates (HTTP 401 invalid_client): load any SDM page on the iMac and grep the
_app-*.js chunk for 'NEXT_PUBLIC_BFF_API_KEY' — the literal key sits right before it.
Verified 2026-10-08 (BioSteel Hydration Mix 883309588741: $12.99 -> $9.69 sale, stock 2).
"""
import json
import re
import sys
import urllib.error
import urllib.request

BASE = "https://prod-sdm-bff.api.loblaw.digital/beauty/v2/shoppersdrugmart"
APIKEY = "r3kEMAxRsQQtyjXiIJOTFNN75vcsJFxH"  # public web key from the SDM _app bundle
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "x-apikey": APIKEY, "x-application-type": "Web", "accept": "application/json",
        "user-agent": UA, "origin": "https://www.shoppersdrugmart.ca",
        "referer": "https://www.shoppersdrugmart.ca/"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:300]}


def ean_of(arg):
    m = re.search(r"variantCode=(\d+)", arg) or re.search(r"BB_(\d+)", arg) or re.fullmatch(r"(\d{6,14})", arg.strip())
    if not m:
        raise SystemExit(f"can't find a product code in {arg!r}")
    return m.group(1)


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _img(v):
    im = (v.get("jsonLd") or {}).get("image")
    if isinstance(im, list):
        im = im[0] if im else None
    if not im:
        im = next((i.get("url") for i in v.get("images") or [] if i.get("url")), None)
    return im


def product(arg, postal="L7M0K5"):
    ean = ean_of(arg)
    st, v = get(f"/product/variantProduct/{ean}/details?province=ON")
    if st != 200:
        return {"code": ean, "status": st, "error": v}
    # A base product can have several size variants; the variant code is the EAN in the URL.
    _, b = get(f"/product/baseProduct/BB_{ean}/details")
    _, f = get(f"/product/{ean}/fulfillment-options?storeId=&postalCode={postal}")
    price = (v.get("price") or {}).get("value")
    eff = (v.get("effectivePrice") or {}).get("value")
    ship = (f.get("fulfillment") or {}).get("shipping") or {}
    vs = (b.get("variantsSummary") or {})
    fb = v.get("featuresBenefit") or ""
    return {
        "code": ean,
        "brand": v.get("brandName"),
        "name": v.get("name"),
        "price": price,
        "sale_price": eff if v.get("isOnSale") and eff != price else None,
        "on_sale": v.get("isOnSale"),
        "badges": [x.get("name") for x in v.get("multiBadges") or v.get("badges") or []],
        "size": v.get("size"),
        "size_unit": next((o.get("unit") for o in vs.get("variantOptions", []) if o.get("code") == ean), None),
        "in_stock": (not v.get("isOutOfStock")) and v.get("purchasable", True),
        "online_stock_level": (v.get("stock") or {}).get("stockLevel"),
        "ship_status": ship.get("status"),
        "ship_eta": ship.get("estimatedDeliveryTime"),
        "variants": [{"code": o.get("code"), "size": o.get("size"), "unit": o.get("unit"),
                      "oos": o.get("isOutOfStock")} for o in vs.get("variantOptions", [])],
        "promo_end": max([p.get("endDate", "") for p in b.get("promotions") or []] or [""]) or None,
        "pco_points": v.get("baseOptimumPoints"),
        "nsf_in_text": bool(re.search(r"NSF", fb + (v.get("description") or ""), re.I)),
        "category": " > ".join(c.get("name", "") for c in b.get("breadCrumbs") or []),
        "image": _img(v),
        "url": v.get("canonicalUrl"),
        "features": strip_html(fb)[:300],
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    postal = "L7M0K5"
    if "--postal" in args:
        i = args.index("--postal"); postal = args[i + 1]; del args[i:i + 2]
    if not args:
        print(__doc__); sys.exit(1)
    for a in args:
        print(json.dumps(product(a, postal), ensure_ascii=False))
