#!/usr/bin/env python3
"""
popeyes_extract.py — Popeye's Supplements Canada (popeyessupplements.com): search + PDP, VPS stdlib.

Ladder step 1 (2026-10-11), no bot wall.
SEARCH  Public Algolia index embedded in every page as `window.S109Algolia`
        (appId O3VAYLLJMW, searchKey, index "products"). The key is REFERER-RESTRICTED:
        without `Referer: https://www.popeyessupplements.com/` Algolia answers
        "Method not allowed with this referer". Hits carry name_en, brand, categories_en,
        skus[], url, image (file under /images/product/), stores[] (store ids that list it).
        Hits have NO price; get it from the PDP.
PDP     schema.org Product JSON-LD: name, sku (UPC), brand, offers.price (CAD),
        offers.availability, image. Flavour options = input[data-attribute-id][aria-label].
        Protein per serving is ONLY in description prose (e.g. "24g GRASS-FED WHEY PROTEIN");
        regex-extracted as `protein_g_claim` — a label claim, not verified. "INFORMED CHOICE
        TESTED" in prose is captured as `cert_claims`; verify it in the Informed Choice registry.
        Note: popeyesonline.com is a parked domain, not the store.

USAGE
  python3 popeyes_extract.py search "<query>" [--n 10]
  python3 popeyes_extract.py pdp <url or /slug> [...]

PDP "description product-description" div is the only place claims are read (the nav menu
has an "Informed Choice" link that would otherwise false-positive). Out-of-stock PDPs carry
price 0.00 -> reported as null.

Verified 2026-10-11: PVL Whey Gold 6lb $79.99 InStock, UPC 627933620015, "24g" protein claim,
"INFORMED CHOICE TESTED" claim; search "whey isolate" -> 79 hits.
"""
import html
import json
import re
import sys
import urllib.request

BASE = "https://www.popeyessupplements.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
ALG_APP, ALG_KEY = "O3VAYLLJMW", "3310acda447294b3c3044019d5bec621"


def get(url):
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept-language": "en-CA"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def search(q, n=10):
    body = json.dumps({"query": q, "hitsPerPage": n}).encode()
    req = urllib.request.Request(
        f"https://{ALG_APP}-dsn.algolia.net/1/indexes/products/query", data=body, method="POST",
        headers={"X-Algolia-Application-Id": ALG_APP, "X-Algolia-API-Key": ALG_KEY,
                 "Content-Type": "application/json", "Referer": BASE + "/", "Origin": BASE,
                 "user-agent": UA})
    j = json.load(urllib.request.urlopen(req, timeout=30))
    for h in j.get("hits", []):
        yield {"name": h.get("name_en"), "brand": h.get("brand"), "skus": h.get("skus"),
               "categories": h.get("categories_en"),
               "image": BASE + "/images/product/" + h["image"] if h.get("image") else None,
               "url": BASE + h.get("url", ""), "n_stores": len(h.get("stores") or [])}


def pdp(url):
    if not url.startswith("http"):
        url = BASE + "/" + url.lstrip("/")
    h = get(url)
    ld = {}
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            j = json.loads(blk, strict=False)
        except ValueError:
            continue
        if j.get("@type") == "Product":
            ld = j
    off = ld.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    d = h.find('class="description product-description"')
    desc_html = h[d:d + 20000] if d >= 0 else ""
    desc_html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", desc_html, flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", desc_html)))
    prot = re.search(r"(\d{1,3}(?:\.\d)?)\s?g\b[^.•]{0,30}?protein", text, re.I)
    certs = sorted({m.group(0).upper() for m in
                    re.finditer(r"informed[ -](?:choice|sport)[^.•]{0,12}|nsf[^.•]{0,25}", text, re.I)
                    if "href" not in m.group(0)})
    img = ld.get("image")
    return {
        "name": html.unescape(ld.get("name") or ""),
        "brand": (ld.get("brand") or {}).get("name") if isinstance(ld.get("brand"), dict) else ld.get("brand"),
        "sku": ld.get("sku"),
        "price": (float(off["price"]) or None) if off.get("price") else None,  # OOS pages say 0.00
        "currency": off.get("priceCurrency"),
        "availability": (off.get("availability") or "").rsplit("/", 1)[-1] or None,
        "flavours": re.findall(r'data-attribute-id="\d+"[^>]*aria-label="([^"]+)"', h),
        "protein_g_claim": float(prot.group(1)) if prot else None,
        "cert_claims": [c.strip() for c in certs][:5],
        "image": img[0] if isinstance(img, list) and img else img,
        "url": url,
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    n = 10
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
