#!/usr/bin/env python3
"""
MEC (mec.ca) product extractor — parses the RENDERED-DOM markdown that
`web_extract` returns for a MEC product page. Verified 2026-08-25.

MEC is a headless Next.js storefront over BigCommerce (store hash
`s-xw5rh7060c`). curl / requests get a hard Cloudflare 403 ("Just a moment...")
from the VPS, and there is NO usable `application/ld+json` block. But the
JS-rendered markdown from web_extract carries everything the skill needs:
title, sale + original price + %OFF, fibre composition (the "Fabric content"
tech-spec row — critical for the natural-fibre gate), colours, sizes, style id,
country of origin, and the BigCommerce CDN image URL.

Which rung worked: web_extract (rendered DOM) — rung 4. Same class as The
Children's Place. NO exit node or Mac delegation needed; web_extract renders
mec.ca clean on the first pass (no Akamai-style intermittent block seen).

HOW TO RUN
  1. Render the PDP:
       web_extract(urls=["https://www.mec.ca/en/product/<style-id>/<slug>"])
     -> saves full page to ~/.hermes/cache/web/www.mec.ca-<hash>.md
  2. Parse it:
       python3 mec_extract.py ~/.hermes/cache/web/www.mec.ca-XXXX.md
     (optionally pass the source URL as 2nd arg to embed it in output)

OUTPUT (JSON)
  {url, title, price, original_price, on_sale, pct_off, sale_flag,
   composition, natural_pct, colors[], sizes[], style_id, made_in,
   image, fabric_weight}

NOTES
  * Per-size STOCK is NOT in the render — MEC loads delivery/pickup availability
    from a separate XHR only after a size is selected ("Select a size to see
    delivery availability"). Treat stock as unknown; verify on the live page
    before recommending. Composition, price, colours, image are fully reliable.
  * Find candidate product URLs via web_search "site:mec.ca <category> <keyword>".
  * VISCOSE/RAYON count as SYNTHETIC per the skill's fibre rule; recycled
    polyester is still polyester (synthetic). merino wool / cotton / linen /
    silk / cashmere / lyocell(=Tencel, plant-derived) count as natural.
"""
import json
import re
import sys

NATURAL = ("cotton", "wool", "merino", "linen", "silk", "cashmere",
           "lyocell", "tencel", "hemp", "alpaca", "mohair", "ramie", "jute")
# tokens that look natural but are NOT, or need care
SYNTH_HINTS = ("polyester", "nylon", "elastane", "spandex", "acrylic",
               "viscose", "rayon", "modal", "polyamide", "polypropylene")

SIZE_TOKENS = ["XXX-Large", "XX-Large", "X-Large", "XX-Small", "X-Small",
               "Small", "Medium", "Large", "XS", "XXL", "XL", "S", "M", "L",
               "One Size"]


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse(md, url=None):
    out = {"url": url}

    # --- Title: product H1 (after the brand link / "Compare") ---
    # Anchor on the LAST "[MEC](.../brands/...)\nCompare\n# <Title>" if present,
    # else the first H1 that isn't a section header.
    m = re.search(r"\nCompare\s*\n#\s+(.+)", md)
    if not m:
        m = re.search(r"^#\s+(.+)$", md, re.M)
    title = _clean(m.group(1)) if m else None
    out["title"] = title
    title_pos = m.start() if m else 0
    body = md[title_pos:]  # anchor extraction after the product title

    # --- Style ID (authoritative product id) ---
    m = re.search(r"Style ID:\s*([0-9]{4}-[0-9]{3})", body)
    out["style_id"] = m.group(1) if m else None

    # --- Price ---
    # Sale shape: "Current price $54.94, original price $109.95~~$109.95~~ 50% OFF"
    price = original = None
    on_sale = False
    pct_off = None
    ms = re.search(r"Current price \$([\d,]+\.\d\d),\s*original price \$([\d,]+\.\d\d)", body)
    if ms:
        price = float(ms.group(1).replace(",", ""))
        original = float(ms.group(2).replace(",", ""))
        on_sale = True
        mp = re.search(r"(\d{1,2})%\s*OFF", body)
        if mp:
            pct_off = int(mp.group(1))
    else:
        # regular price: first standalone "$NN.NN" after the description line
        mp = re.search(r"\n\$([\d,]+\.\d\d)\n", body)
        if mp:
            price = float(mp.group(1).replace(",", ""))
    out["price"] = price
    out["original_price"] = original
    out["on_sale"] = on_sale
    out["pct_off"] = pct_off
    fm = re.search(r"\n(Last chance|Final sale|Clearance)\b", body, re.I)
    out["sale_flag"] = fm.group(1) if fm else None

    # --- Fabric content (tech-spec row) ---
    # Shape: "| Fabric content  | \n  * 46% merino wool\n  * 35% recycled polyester ... |"
    comp = []
    mfc = re.search(r"Fabric content\s*\|\s*(.*?)\n\s*\|", body, re.S)
    if mfc:
        for line in mfc.group(1).splitlines():
            line = line.strip()
            mm = re.match(r"\*\s*(\d{1,3})%\s+(.+)", line)
            if mm:
                comp.append({"pct": int(mm.group(1)),
                             "fibre": _clean(mm.group(2))})
    out["composition"] = comp
    # natural %: sum pct of fibres whose name contains a natural token AND no
    # synthetic hint (so "recycled polyester" -> synthetic).
    nat = 0
    for c in comp:
        f = c["fibre"].lower()
        if any(h in f for h in SYNTH_HINTS):
            continue
        if any(n in f for n in NATURAL):
            nat += c["pct"]
    out["natural_pct"] = nat if comp else None

    # --- Fabric weight ---
    mw = re.search(r"Fabric weight\s*\|\s*([0-9]+\s*gsm)", body)
    out["fabric_weight"] = mw.group(1) if mw else None

    # --- Made in ---
    mmi = re.search(r"Made in\s*\|\s*([A-Za-z ]+?)\s*\|", body)
    out["made_in"] = _clean(mmi.group(1)) if mmi else None

    # --- Colours (swatch bullet list under "Colour:") ---
    colors = []
    mc = re.search(r"Colour:\s*[^\n]*\n(.*?)\n\s*Size:", body, re.S)
    if mc:
        for line in mc.group(1).splitlines():
            cm = re.match(r"\s*\*\s+([A-Za-z][A-Za-z0-9 /'&-]+?)!?\[", line)
            if cm:
                colors.append(_clean(cm.group(1)))
    out["colors"] = colors

    # --- Sizes (glued run after "Size: SelectSize guide") ---
    sizes = []
    msz = re.search(r"Size:\s*SelectSize guide\s*\n([^\n]+)", body)
    if msz:
        run = msz.group(1)
        i = 0
        while i < len(run):
            for tok in SIZE_TOKENS:
                if run[i:i + len(tok)] == tok:
                    sizes.append(tok)
                    i += len(tok)
                    break
            else:
                i += 1
    out["sizes"] = sizes

    # --- Image: the main PRODUCT image, not a 64px colour swatch. ---
    # The hero images render ABOVE the title (so scan the FULL md, not `body`)
    # and live under `.../products/<n>/images/<n>/....(png|jpg)` — the swatches
    # are under `.../attribute_value_images/...preview.jpg`. Prefer `products/`.
    from urllib.parse import unquote
    img = None
    for m2 in re.finditer(r"url=(https%3A%2F%2Fcdn11\.bigcommerce\.com%2F[^&]+)&", md):
        u = unquote(m2.group(1))
        if "/products/" in u and "/images/" in u:
            img = u
            break
    if not img:
        mi2 = re.search(
            r"(https://cdn11\.bigcommerce\.com/[^)\s]*?/products/[^)\s]+\.(?:png|jpg))", md)
        img = mi2.group(1) if mi2 else None
    out["image"] = img

    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: mec_extract.py <cached-web_extract.md> [source-url]")
    path = sys.argv[1]
    url = sys.argv[2] if len(sys.argv) > 2 else None
    with open(path, encoding="utf-8") as f:
        md = f.read()
    print(json.dumps(parse(md, url), indent=2, ensure_ascii=False))
