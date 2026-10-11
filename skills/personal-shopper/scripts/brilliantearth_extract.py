#!/usr/bin/env python3
"""Brilliant Earth (CA) product extractor — parses the rendered-DOM markdown that
`web_extract` returns (curl/requests get a Cloudflare 403 "Verifying" wall from the VPS;
web_extract's headless Crawl4AI renders the PDP clean on the first pass).

GIFT TRACK — fine jewelry (rings, necklaces, earrings, bracelets). There is no textile
fibre content here: "composition" is the precious METAL + gemstone, so the natural-fibre
gate is N/A. What matters for a gift cart: name, live CAD price, in-stock/ship status,
metal, gemstone/carat details, chain length, and image.

USAGE
  # 1. Render the PDP (use the /en-ca/ path for CAD prices — see below):
  #    web_extract(urls=["https://www.brilliantearth.com/en-ca/<Slug>-<STYLE>/"])
  #    -> saves full page to ~/.hermes/cache/web/www.brilliantearth.com-<hash>.md
  # 2. Parse it:
  python3 brilliantearth_extract.py ~/.hermes/cache/web/www.brilliantearth.com-XXXX.md
  #    -> JSON: {title, price, currency, is_setting_only, in_stock, ship_by,
  #              metal, style, gemstone[], chain_length, image, url}

CRITICAL DOMAIN NOTE
  * `/en-ca/...`  -> prices render as "CAD 1,065" (what Sumeet pays). USE THIS.
  * bare `.com/...` (US) -> prices render in USD and design-your-own pieces show
    "$795 (Setting Only)" (metal setting only, needs a separately-chosen centre stone).

FINISHED vs DESIGN-YOUR-OWN
  * Finished piece (birthstone pendant, hoops, studs, pearls, tennis chain): one fixed
    price + "ADD TO BAG" -> buyable as-is. is_setting_only=False.
  * "Design your own" setting (engagement-ring / pendant / stud SETTING): shows
    "$N (Setting Only)" + "CHOOSE THIS SETTING" and the total depends on the centre
    diamond you add. is_setting_only=True -> NOT a single buyable price; flag it in the
    cart ("setting only; centre diamond extra").

Verified 2026-08-28 on 3 live products:
  * BE4DLCAL376 (Lab Alexandrite birthstone pendant, /en-ca/) -> CAD 1,065, in stock, finished
  * BE4D405D (Diamond Halo Pendant, .com)                     -> $795 (Setting Only)
  * BE3D75EL (Claw Prong Diamond Stud Earrings, .com)         -> $750 (Setting Only)
"""
import json
import re
import sys


def _find_url(md, style=None):
    # Prefer the canonical PDP whose slug carries the style id (e.g. ...-BE4DLCAL376-14KY/
    # or ...-BE4D405D-8660534/). style like "BE4DLCAL376-14KY" -> base "BE4DLCAL376".
    if style:
        base = style.split("-")[0]
        m = re.search(r'https://www\.brilliantearth\.com/(?:en-ca/)?[^\s)"]*' + re.escape(base) + r'[^\s)"]*/', md)
        if m:
            return m.group(0)
    m = re.search(r'https://www\.brilliantearth\.com/(?:en-ca/)?[A-Z][^\s)"]*-[A-Z0-9]{5,}[^\s)"]*/', md)
    return m.group(0) if m else None


def parse(md):
    out = {"title": None, "price": None, "currency": None, "is_setting_only": False,
           "in_stock": None, "ship_by": None, "metal": None, "style": None,
           "gemstone": [], "chain_length": None, "image": None, "url": None}

    # Title: the product H1 is a level-1 "#  <name>" line (nav headers are ## / ####).
    for m in re.finditer(r'^#\s+([^#\n].+?)\s*$', md, re.M):
        t = m.group(1).strip()
        if "Brilliant Earth" in t or t.lower().startswith("choose") or "Privacy" in t:
            continue
        out["title"] = t
        title_pos = m.start()
        break
    else:
        title_pos = 0

    tail = md[title_pos:]  # anchor extraction AFTER the product H1 (avoids nav/promo junk)

    # Price. Prefer the first money token right after the H1.
    #   CAD form: "CAD 1,065"  |  USD form: "$795 (Setting Only)" or "$1,995"
    mcad = re.search(r'\bCAD\s*([\d,]+(?:\.\d\d)?)', tail)
    musd = re.search(r'\$\s?([\d,]+(?:\.\d\d)?)\s*(\(Setting Only\))?', tail)
    if mcad:
        out["price"] = float(mcad.group(1).replace(",", ""))
        out["currency"] = "CAD"
    elif musd:
        out["price"] = float(musd.group(1).replace(",", ""))
        out["currency"] = "USD"
        if musd.group(2):
            out["is_setting_only"] = True
    if re.search(r'\(Setting Only\)', tail[:400]):
        out["is_setting_only"] = True

    # Stock / ship: finished pieces show "ADD TO BAG"; settings show "CHOOSE THIS SETTING".
    if re.search(r'\bADD TO BAG\b', tail):
        out["in_stock"] = True
    elif re.search(r'CHOOSE THIS SETTING', tail):
        out["in_stock"] = True  # setting is orderable, but price is setting-only
    ship = re.search(r'ships by\s+([A-Z][a-z]{2,8},?\s+[A-Z][a-z]{2,8}\.?\s*\d{0,2})', tail)
    if ship:
        out["ship_by"] = ship.group(1).strip().rstrip(",")

    # Metal / Style from the "* Metal: ... / Style: ..." detail bullets.
    mm = re.search(r'Metal:\s*\n?\s*([^\n]+?)\s*$', tail, re.M)
    if mm:
        out["metal"] = mm.group(1).strip()
    ms = re.search(r'Style:\s*\n?\s*([A-Z0-9\-]+)', tail)
    if ms:
        out["style"] = ms.group(1).strip()

    cl = re.search(r'Chain Length:\s*([\d]+\s*in\.?)', tail)
    if cl:
        out["chain_length"] = cl.group(1).strip()

    # Gemstone(s): "Type: Lab Grown Alexandrite" / "Type: Diamond" lines under Details.
    for gm in re.finditer(r'Type:\s*(Lab Grown [A-Za-z ]+|Diamond|[A-Z][a-z]+ [A-Za-z]+ Pearl|[A-Za-z]+ Sapphire)', tail):
        g = gm.group(1).strip()
        if g not in out["gemstone"] and "Chain" not in g:
            out["gemstone"].append(g)

    # Image: hero shot. The style-base filename (e.g. BE4D405D_..._top.jpg) is unique, so
    # search the WHOLE doc — design-your-own galleries render BEFORE the H1 (outside `tail`).
    # Fall back to the first product_images URL after the H1 for finished pieces.
    base = out["style"].split("-")[0] if out["style"] else None
    img = None
    if base:
        img = re.search(r'https://image\.brilliantearth\.com/media/product_images/[A-Za-z0-9]{2}/'
                        + re.escape(base) + r'[^\s)"]+\.(?:jpe?g|png|JPG|JPEG)', md)
    if not img:
        img = re.search(r'https://image\.brilliantearth\.com/media/product_images/[A-Za-z0-9]{2}/[^\s)"]+\.(?:jpe?g|png|JPG|JPEG)', tail)
    if img:
        out["image"] = img.group(0)

    out["url"] = _find_url(md, out["style"])
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: brilliantearth_extract.py <rendered-page.md>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        print(json.dumps(parse(f.read()), indent=2, ensure_ascii=False))
