#!/usr/bin/env python3
"""uniqlo_extract.py — Uniqlo Canada via its public commerce JSON API (VPS, stdlib only).

Verified 2026-10-10: plain urllib from the VPS works (no browser, no iMac) as long as the
header `x-fr-clientid: uq.ca.web-spa` is sent. The old `/products/<E-id>` detail endpoint now
answers 302; detail and stock moved under `/price-groups/<pg>/`.

Usage:
  python3 uniqlo_extract.py search "supima cotton t-shirt" [n]
  python3 uniqlo_extract.py pdp E455365-000 [--sizes M,L] [--color 09]

pdp prints: name, composition (string, e.g. "100% Cotton"), natural_pct, origin,
price/promo CAD, promo flag text, url, and per colour → [{size, status, qty, price}].
"""
import json, re, sys, urllib.parse, urllib.request

BASE = "https://www.uniqlo.com/ca/api/commerce/v5/en"
H = {"x-fr-clientid": "uq.ca.web-spa", "accept": "application/json",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"}
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "hemp", "merino",
           "alpaca", "mohair", "ramie", "lambswool")


def get(path):
    req = urllib.request.Request(BASE + path, headers=H)
    j = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if j.get("status") != "ok":
        raise SystemExit(f"API error for {path}: {str(j)[:300]}")
    return j["result"]


def natural_pct(comp):
    # composition may describe several parts ("Body: 100% Cotton/ Rib: ..."); take the first part
    first = re.split(r"[/;]|\bRib\b|\bLining\b", comp or "")[0]
    tot = 0
    for pct, fib in re.findall(r"(\d+)\s*%\s*([A-Za-z ]+)", first):
        if any(n in fib.lower() for n in NATURAL):
            tot += int(pct)
    return tot if re.search(r"\d+\s*%", first) else None


def search(q, n=10):
    r = get(f"/products?q={urllib.parse.quote(q)}&limit={n}&offset=0&httpFailure=true")
    out = []
    for it in r["items"][:n]:
        p = it["prices"]
        out.append({"id": it["productId"], "pg": it.get("priceGroup", "00"), "name": it["name"],
                    "gender": it.get("genderCategory"), "price": p["base"]["value"],
                    "promo": (p.get("promo") or {}).get("value"),
                    "url": f"https://www.uniqlo.com/ca/en/products/{it['productId']}"})
    return out


def pdp(pid, pg="00", sizes=None, color=None):
    d = get(f"/products/{pid}/price-groups/{pg}/details?includeModelSize=false&httpFailure=true")
    s = get(f"/products/{pid}/price-groups/{pg}/l2s?withPrices=true&withStocks=true&httpFailure=true")
    size_name = {z["code"]: z.get("name") or z.get("displayCode") for z in d.get("sizes", [])}
    col_name = {c["displayCode"]: c["name"] for c in d.get("colors", [])}
    imgs = (d.get("images") or {}).get("main") or {}
    flags = set()
    by_col = {}
    for l2 in s["l2s"]:
        cc = l2["color"]["displayCode"]
        if color and cc != color:
            continue
        sz = size_name.get(l2["size"]["code"], l2["size"]["displayCode"])
        if sizes and sz not in sizes:
            continue
        st = s["stocks"].get(l2["l2Id"], {})
        pr = s["prices"].get(l2["l2Id"], {})
        for f in (l2.get("flags") or {}).get("priceFlags", []):
            flags.add(f.get("name"))
        by_col.setdefault(cc, {"color": col_name.get(cc, cc),
                               "image": (imgs.get(cc) or {}).get("image"), "sizes": []})
        by_col[cc]["sizes"].append({"size": sz, "status": st.get("statusCode"),
                                    "qty": st.get("quantity"),
                                    "price": (pr.get("promo") or pr.get("base") or {}).get("value"),
                                    "base": (pr.get("base") or {}).get("value")})
    comp = d.get("composition")
    return {"id": pid, "name": d.get("name"), "composition": comp,
            "natural_pct": natural_pct(comp), "origin": d.get("countriesOfOrigin"),
            "price": d["prices"]["base"]["value"],
            "promo": (d["prices"].get("promo") or {}).get("value"),
            "flags": sorted(f for f in flags if f),
            "url": f"https://www.uniqlo.com/ca/en/products/{pid}", "colors": by_col}


if __name__ == "__main__":
    import urllib.parse
    a = sys.argv[1:]
    if not a or a[0] not in ("search", "pdp"):
        sys.exit(__doc__)
    if a[0] == "search":
        print(json.dumps(search(a[1], int(a[2]) if len(a) > 2 else 10), indent=1))
    else:
        sz = col = None
        if "--sizes" in a:
            sz = a[a.index("--sizes") + 1].split(",")
        if "--color" in a:
            col = a[a.index("--color") + 1]
        print(json.dumps(pdp(a[1], sizes=sz, color=col), indent=1))
