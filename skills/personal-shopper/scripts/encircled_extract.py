#!/usr/bin/env python3
"""
Encircled (encircled.ca) product extractor — personal-shopper skill.

Canada (Toronto), sustainable women's DTC. Slow-fashion basics: TENCEL Modal /
organic-cotton / linen. NATURAL-FIBRE TRAP: the marketing name ("TENCEL Modal
Scuba", "The Comfy ...") hides the blend — some "TENCEL Modal Scuba" styles are
only ~52% TENCEL + 42% polyester (FAIL a 70% gate), while the woven/gauze/jersey
lines are 93-100% TENCEL/cotton (pass). ALWAYS read the actual %.

Platform: Shopify. NO bot wall from the VPS — plain urllib works. Host is
`www.encircled.ca` (apex `encircled.ca` 301-redirects to www).

Method (rungs 2 + 4, both VPS-side):
  * /products/<handle>.js  -> price/compare_at (CENTS), top-level `available`,
    per-variant option1=Colour/option2=Size + `available` (per-size stock),
    `featured_image` (protocol-relative). NO `currency` field -> store default
    is CAD; treat cents as CAD. (JSON-LD price on the PDP is stale/USD — ignore.)
  * PDP HTML  -> composition. It lives in a `<div class="metafield-rich_text_field">`
    under a "The Fabric" heading (🌿). The fibre line takes TWO shapes:
      - leading %:  <li>52% TENCEL Modal, 42% Polyester, 6% Spandex</li>
      - prose:      <li>Made from 100% Organic Cotton Double Gauze fabric</li>
    and a product can list DIFFERENT compositions per colourway. We scan every
    metafield-rich_text_field block, keep the one(s) containing `NN%` fibre
    tokens, and return all (colour_note) + a conservative natural_pct.

TENCEL / Lyocell / Modal are plant-derived -> counted NATURAL here.
Polyester / nylon / spandex / elastane / acrylic -> synthetic.
Viscose/rayon -> synthetic (semi-synthetic) unless told otherwise.

Usage:
  python3 encircled_extract.py <handle-or-url> [<handle-or-url> ...]
  # discover handles:  curl -s https://www.encircled.ca/products.json?limit=250
  #                     or /collections/<c>/products.json

Output: one JSON object per product on stdout (a JSON array).
"""
import sys, json, re, html, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://www.encircled.ca"

NATURAL = ("cotton", "tencel", "lyocell", "modal", "linen", "wool", "silk",
           "cashmere", "hemp", "merino", "alpaca", "jute", "ramie")
# note: modal/tencel/lyocell = plant-derived cellulosics, counted natural.
SYNTHETIC = ("polyester", "nylon", "spandex", "elastane", "acrylic",
             "viscose", "rayon", "polyamide", "lycra", "polyurethane", "acetate")
# any NN% token whose fibre name contains one of these words is a real fibre;
# everything else the regex catches ("of water", "Heavyweight", "gsm") is noise.
FIBRE_WORDS = NATURAL + SYNTHETIC


def fetch(url, accept="text/html"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def handle_of(s):
    s = s.strip()
    if "/products/" in s:
        s = s.split("/products/", 1)[1]
    s = s.split("?")[0].split("#")[0]
    if s.endswith(".js") or s.endswith(".json"):
        s = s.rsplit(".", 1)[0]
    return s.strip("/")


def fibre_pairs(text):
    """Return list of (pct:int, fibre:str) from a chunk of text."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    out = []
    for m in re.finditer(r"(\d{1,3})\s*%\s*([A-Za-z][A-Za-z\u2122®/\- ]{1,28})", text):
        pct = int(m.group(1))
        name = m.group(2).strip(" -")
        # trim trailing filler the regex pulls in after the fibre name
        name = re.split(
            r"\b(fabric|knit|double|gauze|jersey|woven|and|with|heavyweight"
            r"|midweight|lightweight|both|responsib|gsm|of)\b",
            name, 1, flags=re.I)[0].strip()
        # keep only tokens that name a real fibre (drops "95% of water", "295gsm")
        if 0 < pct <= 100 and name and any(f in name.lower() for f in FIBRE_WORDS):
            out.append((pct, name))
    return out


def natural_pct(pairs):
    if not pairs:
        return None
    nat = sum(p for p, n in pairs if any(f in n.lower() for f in NATURAL))
    return nat


def compositions(pdp_html):
    """All fibre blocks found under metafield-rich_text_field divs."""
    blocks = []
    for m in re.finditer(
        r'<div class="metafield-rich_text_field">(.*?)</div>', pdp_html, re.S
    ):
        chunk = m.group(1)
        pairs = fibre_pairs(chunk)
        if pairs:
            # is there a per-colour label right before the fibre <ul>?
            plain = html.unescape(re.sub(r"<[^>]+>", " ", chunk))
            plain = re.sub(r"\s+", " ", plain).strip()
            blocks.append({"pairs": pairs, "text": plain[:200]})
    return blocks


def extract(handle):
    js = json.loads(fetch(f"{BASE}/products/{handle}.js", "application/json"))
    pdp = fetch(f"{BASE}/products/{handle}")

    variants = []
    for v in js.get("variants", []):
        variants.append({
            "colour": v.get("option1"),
            "size": v.get("option2"),
            "price": round(v["price"] / 100.0, 2),
            "available": v.get("available"),
            "sku": v.get("sku"),
        })
    img = js.get("featured_image")
    if img and img.startswith("//"):
        img = "https:" + img

    comps = compositions(pdp)
    # conservative: report the lowest natural_pct across colourways (worst case)
    natpcts = [natural_pct(c["pairs"]) for c in comps if c["pairs"]]
    natpcts = [n for n in natpcts if n is not None]
    nat = min(natpcts) if natpcts else None

    return {
        "handle": handle,
        "url": f"{BASE}/products/{handle}",
        "title": js.get("title"),
        "price": round(js["price"] / 100.0, 2),
        "compare_at_price": (round(js["compare_at_price"] / 100.0, 2)
                             if js.get("compare_at_price") else None),
        "on_sale": bool(js.get("compare_at_price")
                        and js["compare_at_price"] > js["price"]),
        "available": js.get("available"),
        "currency": "CAD",  # .js has no currency; store default is CAD
        "image": img,
        "compositions": [{"fibres": [f"{p}% {n}" for p, n in c["pairs"]],
                          "note": c["text"]} for c in comps],
        "natural_pct_worst": nat,
        "colours": (js.get("options") or [{}])[0].get("values")
        if js.get("options") else None,
        "sizes": next((o.get("values") for o in js.get("options", [])
                       if o.get("name", "").lower() == "size"), None),
        "variants": variants,
        "any_in_stock": any(v["available"] for v in variants),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = []
    for arg in sys.argv[1:]:
        try:
            out.append(extract(handle_of(arg)))
        except Exception as e:
            out.append({"handle": handle_of(arg), "error": str(e)})
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
