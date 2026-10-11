#!/usr/bin/env python3
"""
patagonia_extract.py — parse a Patagonia (patagonia.ca) product page from the
rendered markdown returned by Hermes' `web_extract` tool.

WHY THIS SHAPE: patagonia.ca is HARD-WALLED to the VPS on every direct transport
(curl / requests / .com fallback all return a fake 10-byte "Not found" 404;
the Demandware OCAPI `/s/<site>/dw/shop/...` endpoint 404s; no JSON-LD is exposed
in the rendered markdown; no Shopify endpoints). The ONLY VPS-side path that works
is `web_extract` (Crawl4AI headless Chromium), which renders the SFCC PDP and
returns markdown carrying the fields the natural-fibre gate needs.

  Rung used: web_extract rendered-DOM (rung 4). curl/API = rung 1/2 both DEAD.

HOW TO RUN:
  1. Render the PDP with web_extract (RETRY on "minimal_text"/anti-bot block — the
     Crawl4AI backend is intermittent; the SAME url alternates block/success):
        web_extract(urls=["https://www.patagonia.ca/product/<slug>/<id>.html"])
  2. Save the returned `content` markdown to a file, then:
        python3 patagonia_extract.py pat_page.md
     -> {title, price, currency, composition, natural_pct, style_no,
         country_of_origin, colors[], url, image, sizes[]}

WHAT WORKS / WHAT DOESN'T (verified 2026-09-02):
  * title, price (C$ NN), composition (Materials & Care -> Body/Trim), style no,
    country of origin, colour NAMES  -> all reliable from the markdown.
  * IMAGE URL and PER-SIZE STOCK are NOT in the rendered markdown (web_extract
    strips <img> src and the size-swatch stock state hydrates from a separate XHR).
    For those two fields you must fall back to Mac CDP (read og:image + click size
    swatches) — see retail-bot-wall-bypass. Hence Patagonia is `partial` VPS-side.

Natural-fibre gate: Patagonia's cotton lines ("Regenerative Organic Certified
cotton", "Cotton in Conversion", "Organic Cotton", hemp) are 100%/near-100%
natural and pass easily. But its tech/fleece lines (Capilene, Nano Puff,
recycled polyester, Better Sweater fleece) are predominantly synthetic and FAIL.
The product NAME lies ("Better Sweater" is 100% recycled poly) — always read the
Materials & Care %.
"""
import sys, re, json

NATURAL = ("cotton", "wool", "merino", "linen", "silk", "cashmere", "hemp",
           "lyocell", "tencel", "alpaca", "mohair", "jute", "ramie")

def natural_pct(comp: str) -> int:
    """Sum natural-fibre percentages from a composition string. Counts a fibre once
    even if it appears in both Body and Trim lines (takes the max single %-fibre pair)."""
    total = 0
    seen = set()
    for pct, fibre in re.findall(r'(\d{1,3})%\s*([A-Za-z ]+?)(?=[,\.]|\s*\d|$)', comp):
        f = fibre.strip().lower()
        key = f.split()[0] if f else ''
        if any(n in f for n in NATURAL) and key not in seen:
            total += int(pct)
            seen.add(key)
    return min(total, 100)

def parse(md: str) -> dict:
    # Anchor to the real product H1 (skip promo blocks). The product H1 repeats;
    # take the LAST "# <Title>" that is followed by a price, else the title line.
    title = ""
    m = re.search(r'^#\s+(Men|Women|Kids|Baby|Boys|Girls)[^\n]*', md, re.M)
    if m:
        title = m.group(0).lstrip('# ').strip()
    else:
        m = re.search(r'^#\s+(.+)$', md, re.M)
        title = m.group(1).strip() if m else ""

    # Price: the buy-box uses "C$ NN" (WITH a space); the promo/shipping banner uses
    # "C$NN" (no space) e.g. "C$28 Fast Rate Shipping" — so anchor on the space.
    # On sale the buy-box shows TWO spaced prices: "C$ 59 C$ 28.99" (orig then sale).
    price = None            # the price you pay (sale if on sale, else regular)
    compare_at = None       # struck-through original when on sale, else None
    on_sale = False
    spaced = re.findall(r'C\$\s+(\d+(?:\.\d\d)?)', md)
    if len(spaced) >= 2:
        compare_at = float(spaced[0])
        price = float(spaced[1])
        on_sale = True
    elif spaced:
        price = float(spaced[0])

    style = None
    sm = re.search(r'Style No\.\s*(\d+)', md)
    if sm:
        style = sm.group(1)

    coo = None
    cm = re.search(r'Country of Origin\s*\n+\s*Made in ([^\.\n]+)', md)
    if cm:
        coo = cm.group(1).strip()

    # Composition: collect every "NN% <fibre>" under Materials & Care (Body/Trim).
    mc = md.split("Materials & Care")[-1] if "Materials & Care" in md else md
    comp_bits = re.findall(r'\d{1,3}%[^\n,\.]*', mc)
    composition = "; ".join(dict.fromkeys(b.strip() for b in comp_bits)) or None
    npct = natural_pct(composition) if composition else None

    # Colours: names listed under "Select Color" up to the model/H1 line.
    colors = []
    csec = re.search(r'Select Color\s*\n(.*?)(?:Model is|\n#\s)', md, re.S)
    if csec:
        for line in csec.group(1).splitlines():
            t = line.strip()
            if t and not t.startswith('#') and 'Select' not in t and len(t) < 40:
                colors.append(t)

    return {
        "title": title,
        "price": price,
        "compare_at": compare_at,
        "on_sale": on_sale,
        "currency": "CAD",
        "composition": composition,
        "natural_pct": npct,
        "style_no": style,
        "country_of_origin": coo,
        "colors": colors,
        "image": None,       # not in web_extract markdown — needs Mac CDP (og:image)
        "sizes": [],         # per-size stock not in markdown — needs Mac CDP swatch click
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: patagonia_extract.py <rendered-markdown-file>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
        md = fh.read()
    print(json.dumps(parse(md), indent=2, ensure_ascii=False))
