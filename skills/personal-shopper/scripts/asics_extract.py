#!/usr/bin/env python3
"""
asics_extract.py — parse an ASICS Canada (asics.com/ca/en-ca) product page.

ASICS CA runs on Adobe Commerce / Magento ("Pearl" theme). From the VPS every
curl/requests hit is 403 (Akamai-style header wall), BUT the `web_extract` tool
(Crawl4AI headless Chromium) renders the PDP cleanly on the FIRST pass — no
retry, no exit node, no Mac delegation needed. There is NO usable JSON-LD block
and NO open JSON/`.js` endpoint; all fields come from the rendered markdown.

Footwear only → the skill's natural-fibre gate is N/A (uppers are mesh/synthetic,
no fibre-% published). Live per-size stock is NOT in the render — the PDP shows a
single overall "In stock" / "Out of stock" line; size buttons load their own
availability via XHR the render doesn't fire. That's fine for this skill: it never
orders shoes, and adults pick their own size at checkout.

USAGE
  # 1. Render the PDP with the web_extract tool (returns markdown; also cached to
  #    ~/.hermes/cache/web/<host>-<hash>.md). Save that markdown to a file, then:
  python3 asics_extract.py <rendered_page.md>
  # or pipe:  web_extract output | python3 asics_extract.py -

OUTPUT (JSON to stdout)
  {name, subtitle, price, regular_price, on_sale, availability, in_stock,
   style_no, style_url_id, rating, review_count, image, url}

Verified 2026-08-25 on two live products:
  novablast-5-1011b974-004  -> $149.99 (reg $190.00, on_sale) In stock
  gt-2000-15-1011c235-001   -> $180.00 (no sale) In stock
"""
import sys, re, json


def _clean(md: str) -> str:
    # collapse escaped chars web_extract emits in prices/etc.
    return md.replace("\\$", "$").replace("\u2019", "'")


def parse(md: str) -> dict:
    md = _clean(md)
    out = {
        "name": None, "subtitle": None, "price": None, "regular_price": None,
        "on_sale": False, "availability": None, "in_stock": None,
        "style_no": None, "style_url_id": None, "rating": None,
        "review_count": None, "image": None, "url": None,
    }

    # --- Title: the product H1 ("#  NAME"). Skip the 404 sentinel. ---
    if "THAT PAGE CAN'T BE FOUND" in md.upper() or "OOPS!" in md.upper():
        out["error"] = "404 / product not found"
        return out
    m = re.search(r"^#\s+(.+?)\s*$", md, re.M)
    if m:
        out["name"] = m.group(1).strip()

    # --- Subtitle: the "Men's/Women's/Kids' <Category>" line right after title ---
    m = re.search(r"\b((?:Men's|Women's|Kids'|Unisex|Boys'|Girls')[^\n]*?(?:Shoes|Sandals|Slides|Apparel|Clothing|Socks|Bag|Shorts|Tights|Jacket|Tee|Top)[^\n]*)", md)
    if m:
        out["subtitle"] = m.group(1).strip()

    # --- Price: "As low as $149.99 Regular Price $190.00"  or  "As low as $180.00" ---
    m = re.search(r"As low as\s*\$?([\d,]+\.\d\d)(?:\s*Regular Price\s*\$?([\d,]+\.\d\d))?", md)
    if m:
        out["price"] = float(m.group(1).replace(",", ""))
        if m.group(2):
            out["regular_price"] = float(m.group(2).replace(",", ""))
            out["on_sale"] = out["regular_price"] > out["price"]
    else:
        # fallback: first standalone $NN.NN not inside "Regular Price"
        m = re.search(r"\$([\d,]+\.\d\d)", md)
        if m:
            out["price"] = float(m.group(1).replace(",", ""))

    # --- Availability ---
    if re.search(r"\bOut of stock\b", md, re.I):
        out["availability"], out["in_stock"] = "Out of stock", False
    elif re.search(r"\bIn stock\b", md, re.I):
        out["availability"], out["in_stock"] = "In stock", True

    # --- Style number: "**Style#:**\n1011B974.004" ---
    m = re.search(r"Style#:\s*\**\s*([0-9A-Za-z]+\.[0-9A-Za-z]+)", md)
    if m:
        out["style_no"] = m.group(1)

    # --- Rating / reviews: "4.4 out of 5" + "Read 25 Reviews" ---
    m = re.search(r"([\d.]+)\s+out of 5 stars", md)
    if m:
        out["rating"] = float(m.group(1))
    m = re.search(r"Read (\d+) Reviews?", md)
    if m:
        out["review_count"] = int(m.group(1))

    # --- Main product image (the images.asics.com $product$ render) ---
    m = re.search(r"(https://images\.asics\.com/is/image/asics/[^)\"\s]+?\$product\$[^)\"\s]*)", md)
    if m:
        out["image"] = m.group(1)
    else:
        m = re.search(r"(https://images\.asics\.com/is/image/asics/[^)\"\s]+)", md)
        if m:
            out["image"] = m.group(1)

    # --- Canonical URL + the url style id (…-<style>-<color>) ---
    m = re.search(r"(https://www\.asics\.com/ca/en-ca/[a-z0-9-]+-\d{4,}[a-z]?\d*-\d{3})", md)
    if m:
        out["url"] = m.group(1)
        out["style_url_id"] = out["url"].rsplit("/", 1)[-1]

    return out


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "-":
        md = sys.stdin.read()
        print(json.dumps(parse(md), indent=2, ensure_ascii=False))
    else:
        for path in sys.argv[1:]:
            with open(path, encoding="utf-8") as fh:
                res = parse(fh.read())
            res["_source"] = path
            print(json.dumps(res, indent=2, ensure_ascii=False))
