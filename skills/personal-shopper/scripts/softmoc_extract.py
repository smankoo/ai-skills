#!/usr/bin/env python3
"""softmoc_extract.py — SoftMoc Canada (softmoc.com/ca), VPS stdlib, no bot wall.

Verified 2026-10-10 (recipe from 2026-10-02 still holds).
  grid:   GET /ca/jsonservices/json_itemgridandfilters_1.aspx  (params copied from the page's own XHR)
  detail: POST /ca/getitemdetail_serverload.aspx  -> Sizes[]/WebSizes[] + parallel
          SizeUnavailableCodes[] ('' = available, 'SOLD_OUT'/'UNAVAILABLE'), OnLinePrice, ListPrice,
          FeatureBenefits (materials prose), Thumbnail_X image.
SoftMoc carries NO width variants (standard width only).

Usage:
  python3 softmoc_extract.py brand blundstone blun [n]     # /v/<slug> page + 4-letter vendor code
  python3 softmoc_extract.py grid /womens/winter-boots wos [n]  # dept path + gender code (verified: wos;
                                                               #   "/mens/boots mns" returned 0 — read the page XHR)
  python3 softmoc_extract.py item 2130 [--sizes 10.0,10.5]
"""
import json, re, sys, urllib.parse, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
ROOT = "https://www.softmoc.com"


def _get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def grid(query_string, page_type, base_filter, n=20):
    p = {"queryString": query_string, "pageType": page_type,
         "filtersBaseJson": json.dumps([base_filter]), "filtersJson": "[]",
         "collectionsId": 0, "promopageId": 0, "salePage": 0, "storeId": 0, "getPageInfo": 1}
    j = _get(ROOT + "/ca/jsonservices/json_itemgridandfilters_1.aspx?" + urllib.parse.urlencode(p))
    seen, out = set(), []
    for r in j.get("results") or []:
        for c in r.get("ColoredItems") or []:
            if c.get("ItemID") in seen:
                continue
            seen.add(c.get("ItemID"))
            out.append({"id": c.get("ItemID"), "price": c.get("SalePrice"),
                        "regular": c.get("RegularPrice"), "url": ROOT + (c.get("ItemURL") or "")})
    return out[:n]


def item(item_id, sizes=None):
    body = urllib.parse.urlencode({"itemid": item_id, "syslang": "E", "country": "ca",
                                   "culturename": "en-ca", "itemDetail_Shoes": "Shoes",
                                   "storeid": 0}).encode()
    j = _get(ROOT + "/ca/getitemdetail_serverload.aspx", body)
    codes = j.get("SizeUnavailableCodes") or []
    web = j.get("WebSizes") or []
    sz = []
    for i, s in enumerate(j.get("Sizes") or []):
        if sizes and s not in sizes:
            continue
        sz.append({"size": s, "label": web[i] if i < len(web) else None,
                   "in_stock": (codes[i] if i < len(codes) else "") == "", "code": codes[i] if i < len(codes) else None})
    img = j.get("Thumbnail_X") or ""
    fb = j.get("FeatureBenefits") or ""
    fb = " | ".join(map(str, fb)) if isinstance(fb, list) else str(fb)
    fb = re.sub(r"<[^>]+>", " ", fb)
    return {"id": j.get("ItemID"), "name": j.get("ItemName"), "colour": j.get("Color"),
            "price": (j.get("OnLinePrice") or "").strip(), "list": j.get("ListPrice"),  # "$0.00" = no markdown
            "features": re.sub(r"\s+", " ", fb).strip()[:500],
            "image": ("https:" + img) if img.startswith("//") else img,
            "url": ROOT + "/ca/" + re.sub(r"^/?(ca/)?", "", j.get("ItemURL") or ""), "sizes": sz}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    if a[0] == "brand":
        print(json.dumps(grid("/v/" + a[1], "brandshoeshop", {"FilterType": "V", "Value": a[2]},
                              int(a[3]) if len(a) > 3 else 20), indent=1))
    elif a[0] == "grid":
        print(json.dumps(grid(a[1], "genderdepartmentshoeshop", {"FilterType": "F", "Value": a[2]},
                              int(a[3]) if len(a) > 3 else 20), indent=1))
    elif a[0] == "item":
        s = a[a.index("--sizes") + 1].split(",") if "--sizes" in a else None
        print(json.dumps(item(a[1], s), indent=1))
    else:
        sys.exit(__doc__)
