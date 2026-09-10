#!/usr/bin/env python3
"""
H&M CA (www2.hm.com/en_ca) product extractor — parses the RENDERED-DOM
markdown that `web_extract` returns for an H&M CA product page.
Verified 2026-09-09.

H&M is Akamai-walled to plain curl from the VPS (403 "Access Denied",
Reference #…, on PDPs AND on every JSON service endpoint —
/hmwebservices/…/availability/<art6>.json and /en_ca/getAvailability both
403). There is NO usable JSON-LD and no Shopify layer. BUT the `web_extract`
browser backend (Crawl4AI headless Chromium) renders the PDP clean —
title, price CAD, full fibre composition (the "Composition" bullet under
Materials — critical for the natural-fibre gate), Art. No., colour/fit
description, image.hm.com hero image, and care instructions.

Which rung worked: web_extract (rendered DOM) — rung 4. Same class as
MEC / ASICS / The Children's Place.

⚠️ RATE-LIMITED: the render works on a COLD first pass, but Akamai starts
returning "Akamai block (Reference #)" to the crawler after ~1-2 rapid
requests, and the block persists for several minutes (a 90 s and a 240 s
wait were both still blocked; ~7+ min later it rendered clean again).
Practical rule: fetch H&M pages ONE at a time, spacing requests
>= 5-10 minutes apart, and cache the markdown immediately. Never batch
two H&M URLs in one web_extract call — the second one trips the wall.

HOW TO RUN
  1. Render ONE PDP (find URLs via web_search "site:www2.hm.com en_ca
     productpage <keywords>" — PDP shape is /en_ca/productpage.<10digit>.html,
     where digits = 7-char article + 3-char colourway):
       web_extract(urls=["https://www2.hm.com/en_ca/productpage.1232901003.html"])
  2. Save the returned markdown to a file, then parse:
       python3 hm_extract.py /path/to/render.md

OUTPUT (JSON)
  {url, title, price, art_no, composition, natural_pct, passes_70_gate,
   color, fit, concept, image, description}

NOTES
  * Per-size STOCK is NOT in the render — size picker + availability load
    from a walled XHR after interaction. Treat stock as unknown (the render
    showing "Add to bag" means the default variant is orderable, nothing
    per-size). Verify sizes on the live page / Mac CDP before recommending.
  * Prices are CAD on en_ca.
  * Composition line shape: "Cotton 97%, Elastane 3%" (fibre THEN percent —
    reversed vs most sites). Multi-part garments repeat the pattern
    ("Shell: … Lining: …"); this script sums the FIRST part only.
  * VISCOSE/RAYON/MODAL count as SYNTHETIC per the skill's fibre rule;
    lyocell/Tencel counts natural.
"""
import json
import re
import sys

NATURAL = ("cotton", "wool", "merino", "linen", "silk", "cashmere",
           "lyocell", "tencel", "hemp", "alpaca", "mohair", "ramie", "jute")


def parse(md, url=None):
    out = {"url": url}
    m = re.search(r"URL:\s*(\S+)", md)
    if m and not url:
        out["url"] = m.group(1)

    m = re.search(r"^#\s+(.+)$", md, re.M)
    out["title"] = m.group(1).strip() if m else None

    # price: first standalone $NN.NN line after the title block
    m = re.search(r"^\$([\d,]+\.\d{2})\s*$", md, re.M)
    out["price"] = float(m.group(1).replace(",", "")) if m else None

    m = re.search(r"Art\. No\.:\s*(\d+)", md)
    out["art_no"] = m.group(1) if m else None

    m = re.search(r"Description:\s*([^\n]+)", md)
    out["color"] = m.group(1).strip() if m else None

    m = re.search(r"Fit:\s*([^\n]+)", md)
    out["fit"] = m.group(1).strip() if m else None

    m = re.search(r"Concept:\s*([^\n]+)", md)
    out["concept"] = m.group(1).strip() if m else None

    m = re.search(r"Description & fit\n([^\n]+)", md)
    out["description"] = m.group(1).strip() if m else None

    m = re.search(r"\((https://image\.hm\.com/[^)]+)\)", md)
    out["image"] = m.group(1) if m else None

    # Composition bullet: "* Cotton 97%, Elastane 3%" or "* Cotton 100%"
    m = re.search(r"### Composition\s*\n\*\s*([^\n]+)", md)
    comp = m.group(1).strip() if m else None
    out["composition"] = comp
    nat = 0.0
    if comp:
        for fibre, pct in re.findall(r"([A-Za-z /-]+?)\s+(\d+(?:\.\d+)?)%", comp):
            if any(n in fibre.strip().lower() for n in NATURAL):
                nat += float(pct)
    out["natural_pct"] = nat if comp else None
    out["passes_70_gate"] = (nat >= 70) if comp else None
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: hm_extract.py <render.md> [url]")
    md = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    print(json.dumps(parse(md, sys.argv[2] if len(sys.argv) > 2 else None),
                     indent=2))
