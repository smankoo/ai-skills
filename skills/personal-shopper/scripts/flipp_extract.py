#!/usr/bin/env python3
"""Flipp (backflipp.wishabi.com) weekly-flyer prices for every grocery banner near a postal code.
No key, no login, plain urllib from the VPS. Verified 2026-10-08 for L7M 0K5. It covers Fortinos, No Frills,
RCSS, Loblaws, Zehrs, Metro, Food Basics, Sobeys, FreshCo, Voila, Farm Boy, Longos, Walmart, Costco,
T&T, Btrust, Oceans and others.

Usage:
  flipp_extract.py search "query" [postal] [merchant-substring ...]   # cross-store flyer-item search
  flipp_extract.py flyers [postal] [merchant-substring]               # list current flyers (id, merchant, dates)
  flipp_extract.py items <flyer_id> [name-substring]                  # every item in one flyer
  flipp_extract.py deals "words" [postal] [merchant ...]   # BEST: scan full flyers of grocers, all words must match
Examples:
  flipp_extract.py search "chicken breast" L7M0K5 fortinos "no frills" metro "farm boy" costco
  flipp_extract.py flyers L7M0K5 "farm boy"
  flipp_extract.py items 8174216 apple
Output: one JSON line per item: merchant, name, price, original (regular) price, pre/post price text,
sale_story, valid_from/to, flyer_id, image. This is FLYER data. Flyer prices are sale prices for the
week, with no stock information and often no size. Use pcexpress_extract.py etc. for shelf price, size,
unit price and stock.
"""
import json, sys, urllib.request, urllib.parse

B = "https://backflipp.wishabi.com/flipp"
DEF_POSTAL = "L7M0K5"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
      "Accept": "application/json"}


def get(path, **q):
    url = B + path + "?" + urllib.parse.urlencode(dict(locale="en-ca", **q))
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())


def search(q, postal=DEF_POSTAL, merchants=()):
    d = get("/items/search", postal_code=postal, q=q)
    for i in d.get("items", []):
        m = i.get("merchant_name") or ""
        if merchants and not any(x.lower() in m.lower() for x in merchants):
            continue
        print(json.dumps({"merchant": m, "name": i.get("name"), "price": i.get("current_price"),
                          "original": i.get("original_price"), "pre": i.get("pre_price_text"),
                          "post": i.get("post_price_text"), "sale_story": i.get("sale_story"),
                          "valid_from": (i.get("valid_from") or "")[:10], "valid_to": (i.get("valid_to") or "")[:10],
                          "flyer_id": i.get("flyer_id"), "image": i.get("clean_image_url")}, ensure_ascii=False))


def flyers(postal=DEF_POSTAL, filt=""):
    for f in get("/flyers", postal_code=postal)["flyers"]:
        if filt.lower() in f["merchant"].lower():
            print("%s | %s | %s | %s..%s | %s" % (f["id"], f["merchant"], f.get("name"), f["valid_from"][:10],
                                                f["valid_to"][:10], ",".join(f.get("categories") or [])))


GROCERS = ("fortinos", "no frills", "real canadian superstore", "loblaws", "zehrs", "metro", "food basics",
           "sobeys", "freshco", "voil", "farm boy", "longos", "walmart", "costco", "t&t", "btrust", "wholesale club")


def deals(q, postal=DEF_POSTAL, merchants=()):
    """Scan every current flyer of the chosen merchants (default: GROCERS) and grep item names. Complete,
    unlike /items/search, which returns only the top ~64 hits across ALL merchants (pharmacies crowd it)."""
    want = [m.lower() for m in (merchants or GROCERS)]
    words = q.lower().split()
    for f in get("/flyers", postal_code=postal)["flyers"]:
        m = f["merchant"]
        if not any(w in m.lower() for w in want):
            continue
        for i in get("/flyers/%s" % f["id"]).get("items", []):
            n = (i.get("name") or "")
            if all(w in n.lower() for w in words):
                print(json.dumps({"merchant": m, "flyer": f.get("name"), "name": n, "price": i.get("price"),
                                  "pre": i.get("pre_price_text"), "post": i.get("post_price_text"),
                                  "valid_to": (i.get("valid_to") or "")[:10], "sku": i.get("print_id")},
                                 ensure_ascii=False))


def items(fid, filt=""):
    for i in get("/flyers/%s" % fid).get("items", []):
        if filt.lower() in (i.get("name") or "").lower():
            print(json.dumps({"name": i.get("name"), "brand": i.get("brand"), "price": i.get("price"),
                              "discount": i.get("discount"), "pre": i.get("pre_price_text"),
                              "post": i.get("post_price_text"), "sku": i.get("print_id"),
                              "valid_to": (i.get("valid_to") or "")[:10],
                              "image": i.get("cutout_image_url")}, ensure_ascii=False))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "search":
        search(a[1], a[2] if len(a) > 2 else DEF_POSTAL, a[3:])
    elif a[0] == "deals":
        deals(a[1], a[2] if len(a) > 2 else DEF_POSTAL, a[3:])
    elif a[0] == "flyers":
        flyers(a[1] if len(a) > 1 else DEF_POSTAL, a[2] if len(a) > 2 else "")
    elif a[0] == "items":
        items(a[1], a[2] if len(a) > 2 else "")
