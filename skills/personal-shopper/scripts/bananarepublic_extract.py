#!/usr/bin/env python3
"""
Banana Republic CA (bananarepublic.gapcanada.ca) — extract product fields from a
web_extract rendered-DOM markdown dump.

Banana Republic Canada runs on the **Gap Canada platform** (same as gapcanada.ca /
oldnavy.gapcanada.ca). The live catalog is at `bananarepublic.gapcanada.ca/browse/
product.do?pid=<pid>`. (The separate `www.bananarepublic.ca/products/<slug>.jsp` host
is a marketing "FUI" front that only renders hero/nav copy — do NOT scrape it; use the
gapcanada.ca `product.do` PDP.)

From the VPS, curl / the `/resources/productData/...` JSON API / robots.txt all return
Akamai `Access Denied` (403). But `web_extract` (headless Crawl4AI) renders the PDP
clean on the FIRST pass with NO bot wall — and that render carries: title, current +
sale price, "Now"/"Limited Time" flag, rating (N filled / M ratings), the full image
set (`.../webcontent/NNNN/NNN/NNN/cnNNNNNNNN.jpg`), and the offered size list
(XXS..XXXL as a run-together token).

What the render does NOT contain (verified 2026-09-03):
  - **Fabric composition** — lives in a collapsed "Fabric & Care" accordion whose body
    is not emitted in the rendered markdown. CRITICAL for the natural-fibre gate, so BR
    is only `partial` VPS-side. Get composition via the browser-MCP loaded-tab fetch
    (see Gap/Old Navy `window.__G` recipe — same platform, read the description block)
    or Mac CDP (click the accordion, read innerText).
  - **Per-size stock** — the size run (`XXSXSSMLXLXXL`) is the offered list, not stock.
    For per-size availability use the Gap-platform `--unavailable` label recipe
    (`fds_selector__label--unavailable`) via a loaded tab, same as Gap/Old Navy.

Usage:
  # 1. Render the PDP:
  #    web_extract(urls=["https://bananarepublic.gapcanada.ca/browse/product.do?pid=<pid>"])
  #    -> paste/save the returned `content` to a .md file
  # 2. Parse it:
  python3 bananarepublic_extract.py <render.md>

Output (JSON): {url, pid, title, price, sale_price, on_sale, rating, num_ratings,
                sizes[], image, images[], composition(None), note}
"""
import json
import re
import sys


def parse(md: str) -> dict:
    out = {
        "url": None, "pid": None, "title": None, "price": None, "sale_price": None,
        "on_sale": False, "rating": None, "num_ratings": None, "sizes": [],
        "image": None, "images": [], "composition": None,
        "note": "composition + per-size stock NOT in render — escalate (Gap __G / Mac CDP)",
    }

    m = re.search(r"URL:\s*(\S+)", md)
    if m:
        out["url"] = m.group(1)
        pm = re.search(r"[?&]pid=(\d+)", m.group(1))
        if pm:
            out["pid"] = pm.group(1)

    # Title: first "# <Title>" heading that is NOT the store name / nav
    for h in re.findall(r"^#\s+(.+)$", md, re.M):
        h = h.strip()
        if "Banana Republic" in h and "|" in h:
            continue
        out["title"] = h
        break

    # Product images: the PDP hero set uses /webcontent/ (grid uses www2.assets-gap.com).
    imgs = re.findall(r"\((https://bananarepublic\.gapcanada\.ca/webcontent/[^)]+?\.jpg)\)", md)
    # de-dupe, keep order
    seen = set()
    for u in imgs:
        if u not in seen:
            seen.add(u)
            out["images"].append(u)
    if out["images"]:
        out["image"] = out["images"][0]

    # Prices: collect all CA$NN.NN, take min as sale / max as list when a sale flag is present.
    prices = [float(p) for p in re.findall(r"CA\$(\d+(?:\.\d\d)?)", md)]
    prices = [p for p in prices if p >= 5]  # drop stray "$50+" shipping-threshold noise
    on_sale = bool(re.search(r"\b(Now|Limited Time Offer|Extra \d+% off)\b", md))
    if prices:
        out["price"] = max(prices)
        if on_sale and min(prices) < max(prices):
            out["on_sale"] = True
            out["sale_price"] = min(prices)

    # Rating: "4.69 are filled, 94 Ratings"
    rm = re.search(r"([\d.]+)\s+are filled,\s*([\d,]+)\s+Ratings", md)
    if rm:
        out["rating"] = float(rm.group(1))
        out["num_ratings"] = int(rm.group(2).replace(",", ""))

    # Size run: the "## Size" section emits offered sizes glued together, e.g. "XXSXSSMLXLXXL".
    sm = re.search(r"##\s*Size.*?\n(?:Size Guide\s*\n)?([A-Z0-9]+)\s*\n", md, re.S)
    if sm:
        run = sm.group(1)
        known = ["XXXL", "XXL", "XL", "XS", "XXS", "S", "M", "L"]  # longest-first greedy
        i, seq = 0, []
        while i < len(run):
            for k in ["XXXL", "XXS", "XXL", "XS", "XL", "S", "M", "L"]:
                if run.startswith(k, i):
                    seq.append(k)
                    i += len(k)
                    break
            else:
                i += 1
        # order canonically
        order = {"XXS": 0, "XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "XXL": 6, "XXXL": 7}
        out["sizes"] = sorted(set(seq), key=lambda s: order.get(s, 99))

    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        print(json.dumps(parse(f.read()), indent=2, ensure_ascii=False))
