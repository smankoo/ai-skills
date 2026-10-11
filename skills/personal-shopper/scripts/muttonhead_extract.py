#!/usr/bin/env python3
"""
muttonhead_extract.py — Muttonhead / Mountainhead (mtnhead.com, formerly muttonheadstore.com)

Toronto-made unisex + kids apparel. Strong natural-fibre source: house tees/crews/hoodies
are 100% (combed/organic) cotton, and it also stocks Naked & Famous selvedge denim (100%
cotton / 98-95% cotton-elastane). NO bot wall — pure `urllib` from the VPS.

WHICH RUNG WORKED: Shopify `/products/<handle>.js` ALONE (rung 2). The `.js` payload carries
price (CENTS), per-size `variants[].available` (live stock), image, AND the fibre composition
(embedded in the `description` HTML). No PDP-HTML second fetch and no JSON-LD needed.

GOTCHAS (verified 2026-09-04):
  * muttonheadstore.com 301-redirects to www.mtnhead.com (rebrand). Use the canonical
    www.mtnhead.com host directly, or follow redirects (urllib does by default).
  * `.js` currency field is absent, but `.json` `offers.price_currency` == CAD. Prices ARE CAD.
  * `.json` variants have `available:null` — use `.js` for real per-size stock.
  * Composition lives in the `description` prose, NOT a tidy accordion. body_html contains
    marketing sentences with stray percentages ("10% of sales donated", "5% stretch for...").
    ANCHOR on a fibre whitelist: only accept `NN% <fibre-word>` where the word is a known
    textile fibre. That drops the prose noise and keeps "50% polyester, 37% combed cotton,
    13% rayon" etc.
  * Fibre gate (skill's natural-fibre rule): cotton/wool/linen/silk/cashmere/hemp/lyocell =
    natural; polyester/nylon/spandex/elastane/acrylic/rayon/viscose = synthetic (rayon/viscose
    is semi-synthetic → counted synthetic per skill). "cotton equivalent" (selvedge marketing)
    is treated as cotton.
  * Naked & Famous denim is sold here (vendor field == "Naked and Famous") — dupes the
    nakedandfamous_extract.py catalogue but at CAD list here.

USAGE:
  python3 muttonhead_extract.py <handle-or-url> [<handle-or-url> ...]
  e.g. python3 muttonhead_extract.py work-shirt-trippy-ombre-ivory \
       https://www.mtnhead.com/products/ringer-tee-heather-grey-blue-jay-embroidery

OUTPUT (per product, JSON):
  {url, title, vendor, type, price, compare_at_price, on_sale, currency, available,
   composition, natural_pct, image, sizes[], variants:[{name,price,available,inv_qty}],
   any_in_stock}
"""
import json, re, sys, urllib.request
from html import unescape

HOST = "https://www.mtnhead.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

NATURAL = {"cotton", "wool", "linen", "silk", "cashmere", "hemp", "lyocell",
           "tencel", "merino", "alpaca", "mohair", "ramie", "jute"}
SYNTHETIC = {"polyester", "nylon", "spandex", "elastane", "acrylic", "rayon",
             "viscose", "polyamide", "modal", "polyurethane", "acetate"}
FIBRE_WORDS = NATURAL | SYNTHETIC

# NN%  <fibre word>  — the word must be a known fibre. Allows "combed cotton",
# "cotton equivalent", "Recycled ... nylon" by matching the fibre token anywhere in
# the short trailing phrase.
FIBRE_RE = re.compile(
    r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /\u00a0]{0,30})", re.I)


def handle_of(arg):
    m = re.search(r"/products/([^/?#.]+)", arg)
    if m:
        return m.group(1)
    return arg.strip().rstrip("/")


def fetch_js(handle):
    url = f"{HOST}/products/{handle}.js"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def parse_composition(description):
    """Return (composition_str, natural_pct) using a fibre whitelist."""
    txt = unescape(re.sub(r"<[^>]+>", " ", description or ""))
    txt = txt.replace("\u00a0", " ")
    parts = []          # (pct, fibre_word_normalised)
    seen = set()
    for pct, phrase in FIBRE_RE.findall(txt):
        words = re.findall(r"[A-Za-z]+", phrase)
        idx = next((i for i, w in enumerate(words) if w.lower() in FIBRE_WORDS),
                   None)
        if idx is None:
            continue
        fibre = words[idx].lower()
        # keep the fibre word plus any leading modifier (combed/organic/recycled),
        # drop trailing prose ("cotton crewneck is designed" -> "cotton")
        clean = " ".join(words[max(0, idx - 1):idx + 1]).strip()
        key = (int(pct), fibre)
        if key in seen:
            continue
        seen.add(key)
        parts.append((int(pct), fibre, clean))
    if not parts:
        return None, None
    natural = sum(p for p, f, _ in parts if f in NATURAL)
    comp = ", ".join(f"{p}% {ph}" for p, f, ph in parts)
    return comp, natural


def extract(arg):
    handle = handle_of(arg)
    d = fetch_js(handle)
    comp, nat = parse_composition(d.get("description", ""))
    variants = [{"name": v.get("public_title") or v.get("title"),
                 "price": v["price"] / 100.0,
                 "available": v["available"],
                 "inv_qty": v.get("inventory_quantity")}
                for v in d.get("variants", [])]
    img = d.get("featured_image") or ""
    if img.startswith("//"):
        img = "https:" + img
    price = d.get("price", 0) / 100.0
    cmp = d.get("compare_at_price")
    cmp = cmp / 100.0 if cmp else None
    return {
        "url": f"{HOST}/products/{handle}",
        "title": d.get("title"),
        "vendor": d.get("vendor"),
        "type": d.get("type"),
        "price": price,
        "compare_at_price": cmp,
        "on_sale": bool(cmp and cmp > price),
        "currency": "CAD",
        "available": d.get("available"),
        "composition": comp,
        "natural_pct": nat,
        "image": img,
        "sizes": [v["name"] for v in variants if v["available"]],
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for a in sys.argv[1:]:
        try:
            out.append(extract(a))
        except Exception as e:
            out.append({"arg": a, "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))
