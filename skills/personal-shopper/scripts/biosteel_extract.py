#!/usr/bin/env python3
"""
biosteel_extract.py — BioSteel Canada (biosteel.ca, Shopify, CAD): search + product, VPS stdlib.

Ladder step 1 (2026-10-11). Shopify edge sometimes answers `429 local_rate_limited` (18 bytes)
to EVERY path, including the homepage, for a few minutes after a burst (`/products.json` is the
usual trigger). Back off; the script retries 3x with a 20 s sleep. `web_extract` of
`/search/suggest.json` and the VPS browser both still work during a 429.

SEARCH  /search/suggest.json?q=<q>&resources[type]=product&resources[limit]=10
PRODUCT /products/<handle>.js  -> price (cents), compare_at_price, available, variants[]
        (title "Vanilla / 816g", sku, barcode). Tags hold the label facts:
        "28 grams"  = protein per serving claim; "24 Servings" = servings count.
        price_per_serving = price / servings. PDP HTML is scanned for "NSF CERTIFIED FOR SPORT"
        (badge alt text) and the Supplement Facts image (files/BIO_SuppFacts-*.png).
        These are LABEL claims; verify NSF in the nsfsport.com registry before recommending.

USAGE
  python3 biosteel_extract.py search "<query>" [--n 10]
  python3 biosteel_extract.py product <handle|url> [...]

Verified 2026-10-11: WHEY PROTEIN ISOLATE / Vanilla Milkshake - 24 Servings, $89.99, available,
28 g protein/serving, $3.75/serving, NSF Certified for Sport badge on the PDP.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://biosteel.ca"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")


def get(url, tries=3):
    for i in range(tries):
        req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "*/*",
                                                   "accept-language": "en-CA,en;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(20)
                continue
            raise


def handle_of(x):
    m = re.search(r"/products/([^/?#.]+)", x)
    return m.group(1) if m else x


def search(q, n=10):
    u = (f"{BASE}/search/suggest.json?q={urllib.parse.quote(q)}"
         f"&resources[type]=product&resources[limit]={n}")
    j = json.loads(get(u))
    for p in j["resources"]["results"].get("products", []):
        yield {"title": p["title"], "handle": p["handle"], "price": float(p["price"]),
               "available": p["available"], "url": f"{BASE}/products/{p['handle']}",
               "image": p.get("image")}


def product(h):
    h = handle_of(h)
    j = json.loads(get(f"{BASE}/products/{h}.js"))
    tags = j.get("tags") or []
    prot = next((float(m.group(1)) for t in tags for m in [re.fullmatch(r"(\d+(?:\.\d+)?) grams", t)] if m), None)
    serv = next((int(m.group(1)) for t in tags for m in [re.fullmatch(r"(\d+) Servings?", t, re.I)] if m), None)
    if serv is None:
        m = re.search(r"(\d+) Servings", j["title"], re.I)
        serv = int(m.group(1)) if m else None
    price = j["price"] / 100
    page = get(f"{BASE}/products/{h}")
    facts = re.search(r'(//[^"\s]*?/files/[^"\s]*SuppFacts[^"\s?]*\.(?:png|jpg))', page)
    return {
        "title": j["title"], "price": price,
        "compare_at": (j.get("compare_at_price") or 0) / 100 or None,
        "available": j["available"],
        "variants": [{"title": v["title"], "price": v["price"] / 100, "available": v["available"],
                      "sku": v.get("sku"), "barcode": v.get("barcode")} for v in j["variants"]],
        "protein_g_claim": prot, "servings": serv,
        "price_per_serving": round(price / serv, 2) if serv else None,
        "price_per_25g_protein": round(price / serv / prot * 25, 2) if serv and prot else None,
        "nsf_sport_claim": bool(re.search(r"NSF CERTIFIED FOR SPORT", page, re.I)),
        "informed_choice_claim": bool(re.search(r"informed[ -](?:choice|sport)", page, re.I)),
        "supp_facts_image": ("https:" + facts.group(1)) if facts else None,
        "image": ("https:" + j["featured_image"]) if str(j.get("featured_image", "")).startswith("//") else j.get("featured_image"),
        "url": f"{BASE}/products/{h}",
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
    elif a[0] == "product":
        for x in a[1:]:
            print(json.dumps(product(x), ensure_ascii=False))
