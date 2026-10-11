#!/usr/bin/env python3
"""
sephora_extract.py — parse a Sephora CA product page captured by `web_extract`.

Sephora CA (www.sephora.com/ca/en) is a beauty/personal-care store (gift track).
Its product API (/api/v3/catalog/products/<PID>) is Akamai-walled from the VPS
(403 "Access Denied"), and there is NO usable application/ld+json in the render.
BUT the JS-rendered markdown that `web_extract` returns carries the fields the
gift track needs from the buy-box: product NAME, LIST price, and (when present)
the SALE price + % off. Image, full ingredient list (INCI), and per-variant stock
hydrate from a *separate* XHR and are NOT in the render — so this is a PARTIAL
recipe: good for name+price, escalate to CDP/browser XHR-intercept for image/INCI.

HOW TO RUN
  1. Capture the PDP (retry on Akamai — it's intermittent, a 2nd/3rd call renders):
       web_extract(urls=["https://www.sephora.com/ca/en/product/<slug>-P<id>"])
     web_extract returns the markdown inline; if it's long it also saves the full
     page to ~/.hermes/cache/web/www.sephora.com-<hash>.md — pass that file here.
  2. Parse:
       python3 sephora_extract.py ~/.hermes/cache/web/www.sephora.com-XXXX.md
     or pipe the inline markdown on stdin:
       python3 sephora_extract.py -   < captured.md

OUTPUT (JSON):
  {name, brand, list_price, sale_price, pct_off, on_sale, size, url, source}

VERIFIED 2026-08-27 on two live products:
  - P381145 (First Aid Beauty Ultra Repair Cream Mini): name, $28.00 list,
    $26.60 Auto-Replenish (5% off) — matched the live buy-box.
  - P514193 / P417867 render the same shape (name H1 + "$NN.NN" list line).
Beauty/personal-care -> the natural-fibre gate is N/A for this store.
"""
import json
import re
import sys


def parse(md: str, url: str = "") -> dict:
    # web_extract mangles some UTF-8 (® -> Â®, em/en-dash -> â...); repair.
    clean = md.replace("\u00c2", "")
    clean = clean.replace("\u00e2\u0080\u0093", "-").replace("\u00e2\u0080\u0094", "-")
    clean = clean.replace("\u00e2", "-")  # residual mangled dashes

    # --- URL (first "URL: ..." line the extractor prints, else caller-supplied) ---
    if not url:
        m = re.search(r"^URL:\s*(https?://\S+)", clean, re.M)
        if m:
            url = m.group(1).strip()

    # --- Name: the product H1. The FIRST "# " line is a "<title> | Sephora" echo;
    #     the real product H1 is the one that does NOT end in "| Sephora". ---
    name = ""
    for m in re.finditer(r"^#\s+(.+?)\s*$", clean, re.M):
        cand = m.group(1).strip()
        if cand.lower().endswith("| sephora"):
            continue
        name = re.sub(r"\s+", " ", cand)
        break
    # Fallback: derive from the "<title> | Sephora" line.
    if not name:
        m = re.search(r"^#\s+(.+?)\s*\|\s*Sephora\s*$", clean, re.M)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip()

    # --- Brand: Sephora titles start "<Brand> <Product>"; brand is usually the
    #     leading segment before the product-type words. Best-effort only. ---
    brand = ""
    mt = re.search(r"^#\s+(.+?)\s*\|\s*Sephora\s*$", clean, re.M)
    if mt:
        # e.g. "Ultra Repair Cream Intense Hydration - First Aid Beauty"
        title = mt.group(1)
        if " - " in title:
            brand = title.rsplit(" - ", 1)[-1].strip()

    # --- Prices. List price is the first bare "$NN.NN" (buy-box), which may be
    #     glued to following text: "$28.00or 4 payments...". Sale price shows as
    #     "get it for $26.60 (5% off)" or "$26.60 (Save 5%) $28.00". ---
    prices = [float(x) for x in re.findall(r"\$(\d+(?:\.\d{2})?)", clean)]
    list_price = prices[0] if prices else None

    sale_price = None
    pct_off = None
    msale = re.search(r"get it for \$(\d+(?:\.\d{2})?)\s*\((\d+)%\s*off\)", clean, re.I)
    if not msale:
        msale = re.search(r"\$(\d+(?:\.\d{2})?)\s*\(Save\s*(\d+)%\)", clean, re.I)
    if msale:
        sale_price = float(msale.group(1))
        pct_off = int(msale.group(2))

    # If we found a "(Save N%) $LIST" pattern, the trailing number is the true list.
    m2 = re.search(r"\(Save\s*\d+%\)\s*\$(\d+(?:\.\d{2})?)", clean, re.I)
    if m2:
        list_price = float(m2.group(1))

    # --- Size (e.g. "Size: 2 oz/56.7 mL") ---
    size = ""
    ms = re.search(r"Size:\s*([^\n]+)", clean)
    if ms:
        size = ms.group(1).strip()

    return {
        "name": name,
        "brand": brand,
        "list_price": list_price,
        "sale_price": sale_price,
        "pct_off": pct_off,
        "on_sale": sale_price is not None,
        "size": size,
        "url": url,
        "source": "web_extract-render (partial: no image/INCI/stock)",
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: sephora_extract.py <captured.md | ->")
    if sys.argv[1] == "-":
        md = sys.stdin.read()
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            md = f.read()
    print(json.dumps(parse(md), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
