#!/usr/bin/env python3
"""
childrensplace_extract.py — parse product data out of a The Children's Place (CA)
product page that has already been rendered to markdown by the `web_extract` tool.

The Children's Place (childrensplace.com/ca) is a JS-rendered site behind Akamai.
It has NO usable JSON-LD and NO clean public JSON API discovered, BUT the rendered
markdown that `web_extract` returns carries every field the personal-shopper skill
needs: title, sale/original price, % off, per-size stock, fabric composition, colour
swatches, and Cloudinary image URLs. This parser turns that markdown into a dict.

USAGE
-----
1. In the agent, call web_extract on the PDP URL(s), e.g.:
     web_extract(urls=["https://www.childrensplace.com/ca/p/<slug>-<id>-<colorcode>"])
   web_extract saves the full page to ~/.hermes/cache/web/<host>-<hash>.md
   and prints that path in its footer.
2. Run this on the saved cache file (or any file holding the markdown):
     python3 childrensplace_extract.py ~/.hermes/cache/web/www.childrensplace.com-XXXX.md
   Prints a JSON object. Pass multiple files to get a JSON array.

Akamai note: web_extract intermittently returns
  "Blocked by anti-bot protection: Akamai block" — just retry the URL; a second or
third call usually renders clean (verified 2026-08-15). No exit node needed.

Example output shape:
  {
    "item_no": "1124756_NJ",
    "product_id": "1124756",
    "color_code": "NJ",
    "title": "Boys Uniform Soft Pique Polo - blue",
    "sale_price": 11.0,
    "original_price": 16.95,
    "pct_off": 35,
    "final_sale": false,
    "composition": "100% cotton pique, imported",
    "natural_pct": 100,
    "sizes": [{"size": "XS (4)", "in_stock": true}, ...],
    "colors": ["NAUTICO", "WHITE", "BROOK", ...],
    "image": "https://assets.theplace.com/.../1124756/1124756_NJ.jpg",
    "url": "https://www.childrensplace.com/ca/p/Boys-Uniform-Short-Sleeve-Pique-Polo-1124756-NJ"
  }
"""
import json
import re
import sys

# Fibres counted as natural (lyocell/Tencel is plant-derived — counted natural).
NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell",
           "tencel", "hemp", "merino", "modal-free")  # modal/viscose = synthetic
SIZE_RE = re.compile(r"^(XS|S|M|L|XL|XXL|XXXL)\s*\([\d/]+\)$|^\d{1,2}T$|^\d+/\d+$|^\d{1,2}-\d{1,2}\s?M$")


def natural_pct(comp: str) -> int:
    """Sum natural-fibre percentages from a FABRICATION string like
    '79% cotton, 21% polyester'. Returns int percent (0-100)."""
    total = 0
    for pct, fibre in re.findall(r"(\d+)\s*%\s*([A-Za-z]+)", comp):
        if fibre.lower() in NATURAL:
            total += int(pct)
    return total


def parse(md: str) -> dict:
    out = {}

    # Item # (authoritative id + colour code): "Item #: 1124756_NJ"
    m = re.search(r"Item #:\s*([0-9]+)_([A-Za-z0-9]+)", md)
    if m:
        out["product_id"] = m.group(1)
        out["color_code"] = m.group(2)
        out["item_no"] = f"{m.group(1)}_{m.group(2)}"

    # Title: the "# <Title>" H1 that is the product name (skip nav H1s).
    # IMPORTANT: a "FEATURED PRODUCTS" nav block renders BEFORE the real product
    # and carries its OWN prices/images/%OFF. We must ignore everything before the
    # product H1, so record where the title starts and search only AFTER it.
    title_pos = 0
    for line in md.splitlines():
        mm = re.match(r"^#\s+(Boys|Girls|Baby|Toddler|Kids)\b.+", line.strip())
        if mm:
            out["title"] = line.strip().lstrip("# ").strip()
            title_pos = md.find(line)
            break
    body = md[title_pos:] if title_pos else md

    # Prices. Prefer the explicit "Sale Price:" / "Original Price:" labels — from BODY.
    ms = re.search(r"Sale Price:\s*\$?([\d,]+(?:\.\d\d)?)", body)
    mo = re.search(r"Original Price:\s*\$?([\d,]+(?:\.\d\d)?)", body)
    if ms:
        out["sale_price"] = float(ms.group(1).replace(",", ""))
    if mo:
        out["original_price"] = float(mo.group(1).replace(",", ""))
    # "% OFF" runs together with the price in the render (e.g. "$16.9535% OFF"),
    # so anchor on the CENTS + up-to-2-digit percent to avoid grabbing "9535".
    mp = re.search(r"\.\d\d(\d{1,2})%\s*OFF", body) or re.search(r"\b(\d{1,2})%\s*OFF", body)
    if mp:
        out["pct_off"] = int(mp.group(1))
    if "sale_price" not in out and "original_price" in out:
        out["sale_price"] = out["original_price"]

    out["final_sale"] = "FINAL SALE" in body

    # Composition: "FABRICATION: 100% cotton pique, imported"
    mc = re.search(r"FABRICATION:\s*([^\n]+)", body, re.I)
    if mc:
        comp = mc.group(1).strip()
        out["composition"] = comp
        out["natural_pct"] = natural_pct(comp)

    # Per-size stock. The rendered page lists sizes, then a run of stock states.
    # A size row is followed (within the buybox) by "ADD TO BAG" (in stock) or
    # "OUT OF STOCK". We locate the "Size:" block and pair size labels to the
    # nearest following stock token.
    sizes = []
    lines = [l.strip() for l in body.splitlines()]
    if "Size:" in lines:
        i = lines.index("Size:")
        # collect size labels until we hit the first stock token
        labels, states = [], []
        for l in lines[i + 1:i + 40]:
            if SIZE_RE.match(l):
                labels.append(l)
            elif l in ("ADD TO BAG", "OUT OF STOCK"):
                states.append(l == "ADD TO BAG")
            elif l.startswith("## ") or l == "Product Description":
                break
        # If states line up 1:1 with labels, pair them; else mark unknown.
        for idx, lab in enumerate(labels):
            in_stock = states[idx] if idx < len(states) else None
            sizes.append({"size": lab, "in_stock": in_stock})
    out["sizes"] = sizes

    # Colours: swatch alt-text lines like "NAUTICO![NAUTICO](...swatch...)".
    colors = []
    for m2 in re.finditer(r"^([A-Z0-9 ]{2,20})!\[\1\]\(https://assets\.theplace\.com[^)]*swatch",
                          body, re.M):
        c = m2.group(1).strip()
        if c and c not in colors:
            colors.append(c)
    out["colors"] = colors

    # Main image (first PDP image, drop transform segment for a clean URL).
    mi = re.search(r"(https://assets\.theplace\.com/image/upload/[^)]*?/ecom/assets/products/tcp/[^)]+?\.(?:jpg|png))", body)
    if mi:
        out["image"] = mi.group(1)

    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)
    results = []
    for path in argv[1:]:
        with open(path, encoding="utf-8") as f:
            results.append(parse(f.read()))
    print(json.dumps(results[0] if len(results) == 1 else results, indent=2))


if __name__ == "__main__":
    main(sys.argv)
