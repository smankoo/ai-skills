#!/usr/bin/env python3
"""Long & McQuade (long-mcquade.com, Canada, music gear): search + PDP + per-store stock, plain urllib (VPS).

Usage:
  python3 longmcquade_extract.py search "yamaha p145"          # -> product URLs + names
  python3 longmcquade_extract.py pdp <product-url> [--store Burlington]

Method (verified 2026-10-14):
  * Search: GET /?page=search&SearchGuardContext=header_submit&SearchJs=1&SearchElapsedMs=1500&SearchHp=&SearchTxt=<q>
    Without the SearchGuard/SearchJs/SearchElapsedMs params the server returns an empty results shell
    (the header form's anti-bot guard fills them in JS). Product links look like /<ProductsID>/<Dept>/.../<Name>.htm
  * PDP: server-rendered schema.org Product JSON-LD (name, brand, sku, mpn, price, availability, image).
    Regular price only in text "Regular Price: $X CDN". Page is latin-1, not UTF-8.
  * Stock: POST /includes/AjaxFunctions.php action=ProductAvailability (ProductsID, BrandID, ProductsSku,
    LocationsID) -> JSON {inStock (online html), inStores (html "N stores have stock"), ...}.
    Store list: action=getStoresByProvinceId provinceId=9 (Ontario) -> JSON stores (Burlington = id 8, code l006).
    Per-store stock: GET /instore_stock/<sku>/ (server-rendered table, one row per stocking store) -> instore().
    Dead end: action=checkStockInLocation returns [] for anonymous callers.
"""
import json, re, sys, urllib.parse, urllib.request, html as H

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
BASE = "https://www.long-mcquade.com"


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30)
    return r.read().decode("latin-1")


def post(data):
    req = urllib.request.Request(BASE + "/includes/AjaxFunctions.php", data=urllib.parse.urlencode(data, doseq=True).encode(),
                                 headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                                          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("latin-1")
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def text(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def search(q):
    url = BASE + "/?" + urllib.parse.urlencode({"page": "search", "SearchGuardContext": "header_submit", "SearchJs": 1,
                                                "SearchElapsedMs": 1500, "SearchHp": "", "SearchTxt": q})
    h = get(url)
    out, seen = [], set()
    for m in re.finditer(r'href="(https://www\.long-mcquade\.com/(\d+)/[^"#]+\.htm)[^"]*"', h):
        if m.group(2) in seen:
            continue
        seen.add(m.group(2))
        out.append({"id": m.group(2), "url": m.group(1), "name": m.group(1).rsplit("/", 1)[-1][:-4].replace("-", " ")})
    return out


def stores_on():
    d = post({"action": "getStoresByProvinceId", "provinceId": 9})
    return d if isinstance(d, list) else list(d.values()) if isinstance(d, dict) else []


def pdp(url, store=None):
    h = get(url)
    ld = {}
    for blk in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            j = json.loads(blk)
        except ValueError:
            continue
        if j.get("@type") == "Product":
            ld = j
    off = ld.get("offers", {}) if isinstance(ld.get("offers"), dict) else {}
    reg = re.search(r"Regular Price:\s*\$\s*(?:<[^>]+>\s*)*([\d,]+\.\d\d)", h)
    pid = re.search(r"data-product-id=['\"](\d+)", h)
    bid = re.search(r"data-brand-id=['\"](\d+)", h)
    sku = re.search(r"data-product-sku=['\"]([^'\"]+)", h)
    loc = re.search(r"data-current-store=['\"](\d+)", h)
    res = {"name": ld.get("name"), "brand": (ld.get("brand") or {}).get("name"), "sku": ld.get("sku"), "mpn": ld.get("mpn"),
           "price": off.get("price"), "regular_price": reg.group(1) if reg else None,
           "availability": (off.get("availability") or "").rsplit("/", 1)[-1], "image": ld.get("image"), "url": url}
    if pid:
        a = post({"action": "ProductAvailability", "ProductsID": pid.group(1), "BrandID": bid.group(1) if bid else 0,
                  "ProductsSku": sku.group(1) if sku else ld.get("sku"), "LocationsID": loc.group(1) if loc else 1, "Referer": ""})
        if isinstance(a, dict):
            res["online_stock"] = text(a.get("inStock"))
            res["in_stores"] = text(a.get("inStores")).split(" Province Drop")[0]
            res["in_stock_online_flag"] = a.get("inStock_online")
        else:
            res["availability_raw"] = text(a)[:300]
    if res["sku"]:
        res["stores"] = instore(res["sku"])
        if store:
            res["store"] = [s for s in res["stores"] if store.lower() in (s["name"] or "").lower()] or "not stocked there"
            del res["stores"]
    return res


def instore(sku):
    """GET /instore_stock/<sku>/ -> rows '<tr  data-store-id=N data-sku=..>' (note TWO spaces after <tr),
    first <td> = status ('New in Stock' / used / demo), second <td> = store name + distance from site default."""
    h = get(f"{BASE}/instore_stock/{sku}/")
    parts = re.split(r"<tr\s+data-store-id='(\d+)'", h)
    out = []
    for k in range(1, len(parts), 2):
        row = parts[k + 1].split("</tr>")[0]
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        nm = re.search(r"fs-5 fw-bolder'>([^<]+)</span>", row)
        out.append({"store_id": int(parts[k]), "name": nm.group(1).strip() if nm else None,
                    "status": re.sub(r"\s*(Pick Up in Store|Ship from Store|Reserve).*$", "", text(tds[0])) if tds else None})
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2]), indent=1))
    else:
        store = sys.argv[sys.argv.index("--store") + 1] if "--store" in sys.argv else None
        print(json.dumps(pdp(sys.argv[2], store), indent=1, ensure_ascii=False))
