#!/usr/bin/env python3
"""nike_extract.py: Nike Canada (nike.com/ca) search + PDP + per-size x WIDTH stock. VPS, stdlib only.

Ladder step 1 (plain urllib). No bot wall on nike.com/ca HTML or on the public
api.nike.com/deliver/available_gtins/v3 stock endpoint (verified 2026-10-08).

How Nike models width: each width is a SEPARATE styleColor (e.g. Pegasus 42 Regular
= IB1873-xxx, Pegasus 42 Wide = IR1228-xxx). The PDP's __NEXT_DATA__
props.pageProps.productGroups[] has one group per width (groupLabel "Regular" / "Wide" /
"Extra Wide"), each with products{styleColor: {...sizes[{label, gtins[{gtin}]}], prices}}.
Stock: GET api.nike.com/deliver/available_gtins/v3?filter=styleColor(<SC>)&filter=merchGroup(CA)
returns per-GTIN {available, level: HIGH|MEDIUM|LOW|OOS}. Join gtin -> size label.

Usage:
  nike_extract.py search "<query>"            # -> product URLs (grid wall, ~24 per page)
  nike_extract.py wide [men|women]            # -> the "Wide" running-shoe facet listing
  nike_extract.py pdp <PDP-url> [--sizes 10.5,11] [--width Wide]
     prints JSON: every colourway in every width group with price/sale/image and
     per-size {available, level}. --width filters the groupLabel (case-insensitive substring).
Example:
  nike_extract.py pdp https://www.nike.com/ca/t/pegasus-42-mens-road-running-shoes-wide-8kC2Q4A2/IR1228-001 --sizes 10.5,11 --width wide
"""
import json, re, sys, urllib.parse, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def grid_links(html):
    return list(dict.fromkeys(re.findall(r'href="(https://www\.nike\.com/ca/t/[^"]+)"', html)))


def stock(style_color):
    u = ("https://api.nike.com/deliver/available_gtins/v3?filter=styleColor(%s)&filter=merchGroup(CA)"
         % style_color)
    try:
        objs = json.loads(get(u)).get("objects", [])
    except Exception as e:
        return {"_error": str(e)}
    return {o["gtin"]: {"available": o.get("available"), "level": o.get("level")} for o in objs}


def pdp(url, sizes=None, width=None):
    d = next_data(get(url))
    pp = d["props"]["pageProps"]
    out = []
    for g in pp.get("productGroups", []):
        label = g.get("groupLabel") or ""
        if width and width.lower() not in label.lower():
            continue
        for sc, p in g.get("products", {}).items():
            st = stock(sc)
            pr = p.get("prices") or {}
            img = ""
            for c in p.get("contentImages") or []:
                img = ((c.get("properties") or {}).get("squarish") or {}).get("url", "")
                if img:
                    break
            rows = []
            for s in p.get("sizes") or []:
                if sizes and s.get("label") not in sizes:
                    continue
                gt = (s.get("gtins") or [{}])[0].get("gtin")
                info = st.get(gt, {"available": False, "level": "NOT_LISTED"})
                rows.append({"size": s.get("label"), "label": s.get("localizedLabel"), **info})
            pu = p.get("pdpUrl")
            out.append({
                "width": label, "styleColor": sc,
                "name": (p.get("productInfo") or {}).get("fullTitle"),
                "colour": p.get("colorDescription"),
                "currency": pr.get("currency"), "price": pr.get("currentPrice"),
                "was": pr.get("initialPrice"), "on_sale": (pr.get("currentPrice") or 0) < (pr.get("initialPrice") or 0),
                "status": p.get("statusModifier"),
                "url": pu.get("url") if isinstance(pu, dict) else pu,
                "image": img, "sizes": rows,
            })
    return out


def main(a):
    if not a:
        print(__doc__); return
    if a[0] == "search":
        print(json.dumps(grid_links(get("https://www.nike.com/ca/w?q=" + urllib.parse.quote(a[1]))), indent=1))
    elif a[0] == "wide":
        g = a[1] if len(a) > 1 else "men"
        slug = {"men": "mens-wide-running-shoes-37v7jz7n28vznik1zy7ok",
                "women": "womens-wide-running-shoes-37v7jz5e1x6z7n28vzy7ok"}[g]
        print(json.dumps(grid_links(get("https://www.nike.com/ca/w/" + slug)), indent=1))
    elif a[0] == "pdp":
        sizes = width = None
        if "--sizes" in a:
            sizes = a[a.index("--sizes") + 1].split(",")
        if "--width" in a:
            width = a[a.index("--width") + 1]
        print(json.dumps(pdp(a[1], sizes, width), indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
