#!/usr/bin/env python3
"""
Mountain Warehouse (CA) product extractor — pure urllib, runs on the VPS (NO bot wall).

Mountain Warehouse CA (mountainwarehouse.com/ca) is a Next.js front over BigCommerce
(store `s-nb5it5hcrj`). A plain curl/urllib GET of a product page returns 200 with ALL
the fields the personal-shopper skill needs baked into the STATIC HTML — no JS render,
no XHR, no CDP, no exit node. Value-priced Canadian outdoor apparel; strong natural-fibre
lines (lots of 100% cotton / organic-cotton tees, merino base layers).

Fields, all from the static HTML:
  - title              <title> tag
  - price / was / save aria-label="Original Price: $39.99, Price: $11.99, You save 70%"
  - composition        <h3>Fabric Composition</h3><p>Main fabric: Cotton (organic) 100%, ...</p>
  - natural_pct        computed from the composition (cotton/wool/linen/silk/cashmere/lyocell natural)
  - image              og:image (BigCommerce cdn11 stencil URL)
  - availability       embedded JSON-LD Offer availability (InStock/OutOfStock) — overall
  - sizes[]            VariantOption radio inputs; `disabled=""` on the input => that size is OOS
  - colours[]          Option radio labels (title=) with per-colour swatch image + price

Usage:
  python3 mountainwarehouse_extract.py <product_url> [<product_url> ...]

Product URL shape:  https://www.mountainwarehouse.com/ca/p/<6-digit>/mw/<slug>/
Find candidates:    web_search "site:mountainwarehouse.com/ca <category> <keyword>"

Example output (one dict per URL):
  {"url":..., "title":..., "price":11.99, "was_price":39.99, "save_pct":70,
   "composition":"Main fabric: Cotton (organic) 100%, Rib: Cotton (organic) 97%, Elastane 3%",
   "natural_pct":100, "image":"https://cdn11...jpg", "availability":"InStock",
   "sizes":[{"size":"XXS","in_stock":false}, {"size":"XS","in_stock":true}, ...],
   "colours":[{"name":"Mustard","price":"$11.99"}, ...], "any_in_stock":true}
"""
import sys, re, json, urllib.request, html as _html

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# Natural fibres for the natural-fibre gate. Lyocell/Tencel is plant-derived -> natural.
# Viscose/rayon/modal are semi-synthetic -> counted synthetic (skill rule).
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "merino", "alpaca", "mohair", "jute", "ramie")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def natural_pct(comp):
    """Natural-fibre % of the MAIN fabric only. MW composition strings chain sections
    ('Main fabric: ... , Rib: ... , Lining: ...'); each section sums to 100, so summing
    the whole string double-counts. Isolate the main-fabric section first."""
    if not comp:
        return None
    # main fabric = text after "Main fabric:" up to the next section keyword, else whole string
    m = re.search(r'Main fabric\s*[:\-]?\s*(.*?)(?=,?\s*(?:Rib|Lining|Trim|Filling|Padding|Body|Sole|Insole|Hood|Contrast)\s*[:\-]|$)',
                  comp, re.I)
    seg = m.group(1) if m else comp
    total = 0
    found = False
    # "Cotton (organic) 100%", "Elastane 3%", "55% Linen", "100% cotton"
    for m in re.finditer(r'([A-Za-z][A-Za-z /()\-]*?)\s*[:\-]?\s*(\d{1,3})\s*%'
                         r'|(\d{1,3})\s*%\s*([A-Za-z][A-Za-z /()\-]*)', seg):
        if m.group(2):
            name, pct = m.group(1), int(m.group(2))
        else:
            name, pct = m.group(4), int(m.group(3))
        found = True
        if any(n in name.lower() for n in NATURAL):
            total += pct
    return total if found else None


def extract(url):
    h = fetch(url)
    out = {"url": url}

    m = re.search(r'<title>(.*?)</title>', h, re.S)
    out["title"] = _html.unescape(m.group(1).split("|")[0].strip()) if m else None

    m = re.search(r'aria-label="Original Price:\s*\$?([\d,.]+),\s*Price:\s*\$?([\d,.]+)'
                  r'(?:,\s*You save\s*(\d+)%)?"', h)
    if m:
        out["was_price"] = float(m.group(1).replace(",", ""))
        out["price"] = float(m.group(2).replace(",", ""))
        out["save_pct"] = int(m.group(3)) if m.group(3) else 0
    else:
        # not on sale -> single price aria label "Price: $X"
        m2 = re.search(r'aria-label="Price:\s*\$?([\d,.]+)"', h)
        out["price"] = float(m2.group(1).replace(",", "")) if m2 else None
        out["was_price"] = None
        out["save_pct"] = 0

    m = re.search(r'<h3>Fabric Composition</h3>\s*<p>(.*?)</p>', h, re.S)
    comp = _html.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip()) if m else None
    out["composition"] = comp
    out["natural_pct"] = natural_pct(comp)

    m = re.search(r'property="og:image"\s+content="([^"]+)"', h)
    out["image"] = _html.unescape(m.group(1)) if m else None

    # overall availability from the embedded (escaped) JSON-LD Offer
    m = re.search(r'availability[\\"]*:[\\"]*((?:In|Out\s?Of)Stock)', h)
    out["availability"] = m.group(1) if m else None

    # per-size stock: VariantOption radio inputs; disabled="" => OOS for that size
    sizes = []
    for vm in re.finditer(
            r'(<input[^>]*VariantOption_radioInput[^>]*/>)'
            r'<label[^>]*title="([^"]*)"[^>]*>([^<]*)</label>', h):
        tag = vm.group(1)
        disabled = 'disabled' in tag
        label = _html.unescape(vm.group(3).strip()) or _html.unescape(vm.group(2).strip())
        sizes.append({"size": label, "in_stock": not disabled})
    out["sizes"] = sizes
    out["any_in_stock"] = any(s["in_stock"] for s in sizes) if sizes else \
        (out["availability"] == "InStock")

    # colours: Option radio labels with a swatch + price span (label carries title= then class=)
    colours = []
    for cm in re.finditer(
            r'<label[^>]*title="([^"]+)"[^>]*Option_radioLabel[\s\S]{0,700}?'
            r'Option_price[^>]*>([^<]+)</span>', h):
        colours.append({"name": _html.unescape(cm.group(1)), "price": cm.group(2)})
    out["colours"] = colours

    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    res = [extract(u) for u in sys.argv[1:]]
    print(json.dumps(res if len(res) > 1 else res[0], indent=2, ensure_ascii=False))
