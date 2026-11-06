#!/usr/bin/env python3
"""joefresh_extract.py — Joe Fresh Canada (joefresh.com/ca), VPS stdlib, no browser.

Verified 2026-10-10. Plain urllib with a desktop Chrome UA gets HTTP 200, and the Next.js
`__NEXT_DATA__` carries everything server-side:
  search:  /ca/search?query=<q>:relevance   (must be `query=`; `q=`/`text=` are silently ignored
           and return the default 5,679-item list; without `:relevance` the page has no __NEXT_DATA__)
           -> props.pageProps.initialState.search.getSearchData.response.products[]
  PDP:     /ca/<slug>/p/<CODE>_EA
           -> props.pageProps.initialState.pdp.getPdpData.response
              name, regularPrice, salePrice, badgeValue, details[] (fibre e.g. "100% Cotton"),
              sizes[] {size, disabled (true = sold out online), liam (per-size SKU), imageList}
              availability {isDisabledOnline, bopisAvailable}, imageList[]

Usage:
  python3 joefresh_extract.py search "men crew sweater" [n]
  python3 joefresh_extract.py pdp https://www.joefresh.com/ca/<slug>/p/<CODE>_EA [--sizes M,L]
"""
import json, re, sys, urllib.parse, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
ROOT = "https://www.joefresh.com/ca"
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "hemp", "merino",
           "alpaca", "mohair", "ramie")


def next_data(url):
    html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                  timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise SystemExit(f"no __NEXT_DATA__ at {url} ({len(html)} bytes)")
    return json.loads(m.group(1))["props"]["pageProps"]


def natural_pct(lines):
    for ln in lines:
        hits = re.findall(r"(\d+)\s*%\s*([A-Za-z ]+)", ln)
        if hits:
            return sum(int(p) for p, f in hits if any(n in f.lower() for n in NATURAL)), ln
    return None, None


def search(q, n=20):
    q = q if ":" in q else q + ":relevance"
    pp = next_data(f"{ROOT}/search?query={urllib.parse.quote(q)}")
    r = pp["initialState"]["search"]["getSearchData"]["response"]
    out = {"term": pp.get("searchTerm"), "total": (r.get("pagination") or {}).get("totalNumberOfResults"),
           "items": []}
    for p in r.get("products", [])[:n]:
        out["items"].append({"name": p["name"], "code": p["code"], "colour": p.get("colorCode"),
                             "price": p.get("salePrice"), "regular": p.get("regularPrice"),
                             "badge": p.get("badgeValue"),
                             "sizes_in": [s["size"] for s in p.get("sizes", []) if not s.get("disabled")],
                             "url": ROOT + p["url"]})
    return out


def pdp(url, sizes=None):
    r = next_data(url)["initialState"]["pdp"]["getPdpData"]["response"]
    pct, comp = natural_pct(r.get("details") or [])
    sz = [{"size": s["size"], "in_stock": not s.get("disabled"), "sku": s.get("liam")}
          for s in r.get("sizes", []) if not sizes or s["size"] in sizes]
    return {"name": r.get("name"), "code": r.get("code"), "colour": r.get("colorCode"),
            "price": r.get("salePrice"), "regular": r.get("regularPrice"), "badge": r.get("badgeValue"),
            "composition": comp, "natural_pct": pct, "details": r.get("details"),
            "online_disabled": (r.get("availability") or {}).get("isDisabledOnline"),
            "image": (r.get("imageList") or [None])[0], "sizes": sz, "url": url}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("search", "pdp"):
        sys.exit(__doc__)
    if a[0] == "search":
        print(json.dumps(search(a[1], int(a[2]) if len(a) > 2 else 20), indent=1))
    else:
        s = a[a.index("--sizes") + 1].split(",") if "--sizes" in a else None
        print(json.dumps(pdp(a[1], s), indent=1))
