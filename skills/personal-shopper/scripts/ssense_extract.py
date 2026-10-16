#!/usr/bin/env python3
"""SSENSE (ssense.com/en-ca) extractor — plain curl works (verified 2026-10-15), no browser needed.

Usage:
  ssense_extract.py list <category-path> [pages]   # e.g. men/coats 6  -> prints product URLs
  ssense_extract.py pdp <url> [<url>...]            # JSON per product: name, brand, price CAD,
                                                    # composition, description, sizes+stock, image
PDP mechanics: ld+json has name/brand/price(CAD)/availability/image (image has __IMAGE_PARAMS__
placeholder -> replace with 'f_auto,c_limit,w_640'). Composition + per-size stock live in the
Next.js RSC flight payload (escaped JSON): "compositionByLanguage":{"en":...}, "sizes":[{name,stock}].
"""
import json, re, subprocess, sys, html as H

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"

def get(url):
    return subprocess.run(["curl", "-s", "-L", "--max-time", "30", "-A", UA, url],
                          capture_output=True, text=True).stdout

def lst(cat, pages=5):
    seen = []
    for p in range(1, pages + 1):
        h = get(f"https://www.ssense.com/en-ca/{cat}?page={p}")
        new = [u for u in dict.fromkeys(re.findall(r'/en-ca/men/product/[^"\\?]+', h)) if u not in seen]
        if not new:
            break
        seen += new
    return ["https://www.ssense.com" + u for u in seen]

def pdp(url):
    h = get(url)
    out = {"url": url}
    for s in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            d = json.loads(s)
        except Exception:
            continue
        if d.get("@type") == "Product":
            out.update(name=d["name"], brand=d["brand"]["name"], price=d["offers"]["price"],
                       currency=d["offers"]["priceCurrency"], availability=d["offers"]["availability"],
                       image=d.get("image", "").replace("__IMAGE_PARAMS__", "f_auto,c_limit,w_640"))
    u = h.replace('\\"', '"')
    m = re.search(r'"compositionByLanguage":\{"en":"(.*?)"\}', u)
    out["composition"] = m.group(1) if m else None
    m = re.search(r'"sizes":(\[\{"id".*?\}\])', u)
    if m:
        try:
            out["sizes"] = {x["name"]: x.get("stock") for x in json.loads(m.group(1))}
        except Exception:
            out["sizes"] = m.group(1)[:300]
    m = re.search(r'"descriptionByLanguage":\{"en":"(.*?)"', u) or re.search(r'"description":\{"en":"(.*?)"', u)
    out["description"] = m.group(1)[:900] if m else None
    m = re.search(r'"regularPrice":(\d+)', u)
    out["regular"] = int(m.group(1)) if m else None
    return out

if __name__ == "__main__":
    if sys.argv[1] == "list":
        print("\n".join(lst(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5)))
    else:
        for u in sys.argv[2:]:
            print(json.dumps(pdp(u)))
