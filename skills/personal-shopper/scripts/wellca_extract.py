#!/usr/bin/env python3
"""
wellca_extract.py — Well.ca (CA online pharmacy / beauty / grocery): search + product page.

Ladder step 1: plain urllib from the VPS, no bot wall (2026-10-11). Old osCommerce/Zen-style
site, server-rendered HTML in LATIN-1 (decode as latin-1 / cp1252, not utf-8).

USAGE
  python3 wellca_extract.py search "<query>" [--n 20]
  python3 wellca_extract.py pdp <product URL> [<url> ...]

SEARCH  GET https://well.ca/searchresult.html?keyword=<q>
        tiles = div.product-item[data-product=<id>]; name in .product_grid_info_top_text_container,
        size in .product_grid_info_subtitle, price in .product_grid_price; on sale the tile has
        .product_grid_original_price + .product_grid_new_price.
PDP     itemprop="price" (current, 4 decimals), <meta itemprop="availability" content="InStock">,
        og:image, size .product-info__subtitle, INGREDIENTS in #pills-ingredients (full INCI list),
        brand a.product-info__brand. JSON-LD has name/image/sku/brand/rating but NO offers.
OUTPUT  JSON lines.

Verified 2026-10-11: CeraVe Foaming Facial Cleanser 355 mL $20.99 InStock (+ INCI list);
CeraVe Hydrating Cleanser 355 mL $18.89 (was $20.99).
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept-language": "en-CA"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def money(s):
    m = re.search(r"\$\s*([\d,]+\.\d{2})", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def first(rx, s, default=None, flags=re.S):
    m = re.search(rx, s, flags)
    return m.group(1) if m else default


def search(q, n=20):
    h = get("https://well.ca/searchresult.html?keyword=" + urllib.parse.quote_plus(q))
    out = []
    for box in re.split(r'<div id="pid-\d+"', h)[1:]:
        pid = first(r'data-product="(\d+)"', box)
        url = first(r'href="(https://well\.ca/products/[^"]+)"', box)
        if not pid or not url:
            continue
        pr = first(r'class="product_grid_price">(.*?)</div>', box, "")
        new, orig = money(first(r'product_grid_new_price">([^<]+)', pr, "")), \
            money(first(r'product_grid_original_price">([^<]+)', pr, ""))
        out.append({
            "id": pid,
            "name": clean(first(r'product_grid_info_top_text_container">(.*?)</div>', box, "")),
            "size": clean(first(r'product_grid_info_subtitle">(.*?)</div>', box, "")),
            "brand": (re.search(r'"brand":"([^"]*)"', box) or [None, None])[1],
            "price": new if new is not None else money(pr),
            "old_price": orig if new is not None else None,
            "image": first(r'<img src="([^"]+)"', box),
            "url": url,
        })
        if len(out) >= n:
            break
    return out


def pdp(url):
    h = get(url)
    price = first(r'itemprop="price">([\d.]+)<', h)
    avail = first(r'<meta itemprop="availability" content="([^"]+)"', h) or \
        first(r'og:availability" content="([^"]+)"', h)
    block = first(r'class="product-info__price">(.*?)<klarna', h, "") or ""
    prices = [money(x) for x in re.findall(r"\$[\d,]+\.\d{2}", block)]
    old = max(prices) if prices and price and max(prices) > float(price) + 0.001 else None
    return {
        "name": clean(first(r'class="product-info__title"[^>]*>(.*?)</span>', h, "")) or
        clean(first(r'og:title" content="([^"]+)"', h, "")),
        "brand": clean(first(r'class="product-info__brand">(.*?)</a>', h, "")),
        "size": clean(first(r'class="product-info__subtitle">(.*?)</p>', h, "")),
        "price": float(price) if price else None,
        "old_price": old,
        "availability": avail,
        "in_stock": bool(avail and avail.lower() == "instock"),
        "ingredients": clean(first(r'id="pills-ingredients".*?itemprop="features"[^>]*>(.*?)</div>\s*</div>', h, "")) or None,
        "image": first(r'og:image" content="([^"]+)"', h),
        "url": url,
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    n = 20
    if "--n" in a:
        i = a.index("--n"); n = int(a[i + 1]); del a[i:i + 2]
    if not a:
        print(__doc__); sys.exit(1)
    if a[0] == "search":
        for r in search(" ".join(a[1:]), n):
            print(json.dumps(r, ensure_ascii=False))
    elif a[0] == "pdp":
        for u in a[1:]:
            print(json.dumps(pdp(u), ensure_ascii=False))
