#!/usr/bin/env python3
"""L.L.Bean Canada (llbean.ca) product extractor — pure urllib, VPS-side, NO bot wall.

Stack: Salesforce Commerce Cloud (SFCC/Demandware, site id `Sites-llbeancanada-Site`).
The gold path is the storefront's own `Product-Variation` controller, which returns
one JSON blob with name, live CAD price, LIVE NUMERIC STOCK (`availability.stockLevel`),
per-attribute selectable flags (color / customcut / size), images, and the long
description (which carries fibre composition, e.g. "100% cotton").

Usage:
    python3 llbean_extract.py <pid> [<pid> ...]
    python3 llbean_extract.py 42272 1000292475

    # or from a PDP URL: the pid is the number in /llb/shop/<pid>.html
    python3 llbean_extract.py "https://www.llbean.ca/llb/shop/42272.html"

Output: one JSON object per product on stdout, e.g.
    {"pid": "42272", "name": "Men's Scotch Plaid Flannel Shirt, Traditional Fit",
     "price": 99.95, "currency": "CAD", "in_stock": true, "stock_level": 1761,
     "composition": "100% cotton", "image": "https://cdni.llbean.net/is/image/wim/...",
     "colors": [["Grey Stewart", true], ...], "cuts": [...], "sizes": [...],
     "url": "https://www.llbean.ca/llb/shop/42272.html"}

Notes:
- `stockLevel` is only populated when a FULL variant (color+customcut+size) is
  selected; this script auto-selects the first selectable value of each attribute.
  For a specific size, pass dwvar overrides: llbean_extract.py 42272 size=13
  (attribute value ids come from the first run's output).
- `selectable: false` on a color/cut/size value = that variant is sold out.
- Composition lives in `longDescription` prose ("Made of premium Portuguese
  flannel in 100% cotton") and in the PDP "Fabric & Care" <li> list; the JSON
  route is enough for the fibre gate. If no % found, verify on the PDP.
- Prices are CAD (`price.sales.currency == "CAD"`).
Verified 2026-09-11 on pids 42272, 124345, 1000292475.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.llbean.ca/on/demandware.store/Sites-llbeancanada-Site/default/Product-Variation"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def get_json(qs: str) -> dict:
    req = urllib.request.Request(f"{BASE}?{qs}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pid_from_arg(arg: str) -> str:
    m = re.search(r"/llb/shop/(\d+)", arg)
    return m.group(1) if m else arg


def extract(pid: str, overrides: dict) -> dict:
    # Pass 1: bare pid to learn the variation attributes.
    # GOTCHA: the dwvar_* param prefix uses an INTERNAL master pid that can differ
    # from the display pid (e.g. display 1000292475 -> dwvar_5799541_color).
    # Never construct dwvar params yourself — each variation value carries its own
    # ready-made `url`; follow those sequentially (color -> customcut -> size).
    p = get_json(f"pid={pid}&quantity=1")["product"]
    sel = {}
    for _ in range(4):  # one hop per attribute, until all selected
        advanced = False
        for va in p.get("variationAttributes") or []:
            aid = va["attributeId"]
            if aid in sel:
                continue
            want = overrides.get(aid)
            pick = None
            for v in va.get("values", []):
                if want and want.lower() not in (str(v["id"]).lower(), v["displayValue"].lower()):
                    continue
                if v.get("selectable") and v.get("url"):
                    pick = v
                    break
            if pick:
                sel[aid] = pick["displayValue"]
                qs = urllib.parse.urlparse(pick["url"]).query
                p = get_json(qs)["product"]
                advanced = True
                break
        if not advanced:
            break
    p2 = p

    ld = re.sub(r"<[^>]+>", " ", p2.get("longDescription") or "")
    comp = re.findall(r"\d+% ?[A-Za-z][A-Za-z /-]*", ld)
    avail = p2.get("availability") or {}
    imgs = (p2.get("images") or {}).get("large") or []

    def vals(aid):
        for va in p2.get("variationAttributes") or []:
            if va["attributeId"] == aid:
                return [[v["displayValue"], bool(v.get("selectable"))] for v in va.get("values", [])]
        return []

    return {
        "pid": pid,
        "name": p2.get("productName"),
        "price": (p2.get("price") or {}).get("sales", {}).get("value"),
        "currency": (p2.get("price") or {}).get("sales", {}).get("currency"),
        "in_stock": bool(p2.get("available")),
        "stock_level": avail.get("stockLevel"),
        "availability_msg": (avail.get("messages") or [None])[0],
        "selected": sel,
        "composition": "; ".join(dict.fromkeys(c.strip() for c in comp)) or None,
        "image": imgs[0]["url"] if imgs else None,
        "colors": vals("color"),
        "cuts": vals("customcut"),
        "sizes": vals("size"),
        "url": f"https://www.llbean.ca/llb/shop/{pid}.html",
    }


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    pids, overrides = [], {}
    for a in args:
        if "=" in a and not a.startswith("http"):
            k, v = a.split("=", 1)
            overrides[k] = v
        else:
            pids.append(pid_from_arg(a))
    for pid in pids:
        print(json.dumps(extract(pid, overrides), ensure_ascii=False))


if __name__ == "__main__":
    main()
