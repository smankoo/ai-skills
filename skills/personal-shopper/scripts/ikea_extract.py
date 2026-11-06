#!/usr/bin/env python3
"""
IKEA CA product extractor — parses the rendered-DOM markdown that web_extract
returns for an ikea.com/ca/en product page.

WHY RENDERED-DOM (rung 4): IKEA is behind Cloudflare. From the VPS, plain curl /
urllib to the PDP, to /products/<id>.json, to the iows availability endpoint, and
to api.ingka.ikea.com ALL return HTTP 403 ("Access Denied", Cloudflare + Akamai).
There is NO usable application/ld+json block on the PDP either. But web_extract
(headless Chromium / Crawl4AI) PASSES the passive Cloudflare check and returns the
fully-rendered page, which carries everything the skill needs EXCEPT live stock
(see caveat). No exit node or Mac delegation required.

USAGE
  # 1. Render the PDP with web_extract (tool call, not this script):
  #      web_extract(urls=["https://www.ikea.com/ca/en/p/<slug>-<article>/"])
  #    -> saves the full page to ~/.hermes/cache/web/www.ikea.com-<hash>.md
  # 2. Parse it:
  python3 ikea_extract.py ~/.hermes/cache/web/www.ikea.com-XXXX.md
  # optional: pass the source URL so it lands in the output
  python3 ikea_extract.py <file.md> "https://www.ikea.com/ca/en/p/<slug>-<article>/"

OUTPUT (JSON to stdout)
  {url, name, price, currency, article_no, composition, natural_pct,
   is_textile, image, rating, reviews}

FIELD NOTES (verified 2026-08-24 on BILLY bookcase 205.220.46 = furniture, and
GURLI cushion cover 105.987.77 = textile, 100% cotton):
  name        H1 line `# <NAME>` (strip the trailing markdown link)
  price       `Price $ 7.99` anchor (the visible `$N.NN` label; IKEA has no sale
              strike in the render — the shown price is the live price)
  article_no  the `NNN.NNN.NN` line that appears right after the series name block
  composition the `#### Material\n<text>` block under "Materials and care".
              Furniture -> board/foil/plastic words (no fibre %); textiles ->
              e.g. "100 % cotton" / "55 % linen, 45 % viscose".
  natural_pct sum of natural-fibre % (cotton/wool/linen/silk/cashmere/lyocell/
              hemp/jute/ramie/down/feather/leather/lyocell). Only meaningful for
              textiles; None for furniture (is_textile=False -> gate N/A).
  image       first products/... _s5.jpg (strip the ?f= size query for full res)
"""
import json
import re
import sys

NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "lyocell", "tencel",
           "hemp", "jute", "ramie", "down", "feather", "leather", "merino",
           "mohair", "alpaca", "lambswool")
SYNTH_HINT = ("particleboard", "fiberboard", "fibreboard", "foil", "plastic",
              "paint", "steel", "metal", "glass", "polypropylene", "veneer",
              "foam", "board", "acrylic", "melamine")


def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse(md, url=None):
    out = {"url": url, "name": None, "price": None, "currency": "CAD",
           "article_no": None, "composition": None, "natural_pct": None,
           "is_textile": False, "image": None, "rating": None, "reviews": None}

    # --- name: the product H1 (skip category/nav H1s which have no trailing link) ---
    # PDP H1 looks like: "#  GURLI Cushion cover, unbleached, [65x65 cm ...](url)"
    for m in re.finditer(r"(?m)^#\s+(.+)$", md):
        line = m.group(1)
        # the real product H1 carries the size as a markdown link at the end
        cand = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)  # unwrap md links
        cand = _clean(cand)
        if cand and cand.lower() not in ("products", "billy bookcases"):
            out["name"] = cand
            break

    # --- price: visible label "Price $ 7.99" (space-tolerant) ---
    m = re.search(r"Price\s*\$\s*([\d,]+\.\d{2})", md)
    if not m:
        m = re.search(r"\$\s*([\d,]+\.\d{2})\s*Price", md)
    if m:
        out["price"] = float(m.group(1).replace(",", ""))

    # --- article number: NNN.NNN.NN ---
    m = re.search(r"\b(\d{3}\.\d{3}\.\d{2})\b", md)
    if m:
        out["article_no"] = m.group(1)

    # --- composition: the "#### Material" block (take the first, dedup repeats) ---
    m = re.search(r"####\s*Material\s*\n(.+?)(?:\n####|\n\n|\nCare|$)", md,
                  re.DOTALL | re.IGNORECASE)
    if m:
        comp = _clean(m.group(1))
        out["composition"] = comp
        low = comp.lower()
        # textile if it names a fibre or carries fibre %; else furniture/hard-good
        has_pct = bool(re.search(r"\d+\s*%", comp))
        names_fibre = any(f in low for f in NATURAL)
        looks_hard = any(h in low for h in SYNTH_HINT)
        out["is_textile"] = (has_pct or names_fibre) and not (looks_hard and not has_pct)
        if out["is_textile"]:
            nat = 0.0
            found_any_pct = False
            # explicit percentages: "100 % cotton", "55 % linen"
            for pm in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*([a-z/ ]+)", low):
                found_any_pct = True
                pct = float(pm.group(1))
                fibre = pm.group(2)
                if any(f in fibre for f in NATURAL):
                    nat += pct
            if not found_any_pct and names_fibre:
                # bare "Cotton" with no % and no synthetic named -> treat 100
                if not any(s in low for s in ("polyester", "nylon", "acrylic",
                                              "elastane", "spandex", "viscose",
                                              "rayon", "polyamide")):
                    nat = 100.0
            out["natural_pct"] = round(nat, 1)

    # --- image: first rendered product image, full-res (drop ?f= size query) ---
    m = re.search(r"(https://www\.ikea\.com/ca/en/images/products/[^\s)\"?]+\.jpg)",
                  md)
    if m:
        out["image"] = m.group(1)

    # --- rating / reviews ---
    m = re.search(r"Review:\s*([\d.]+)\s*out of 5", md)
    if m:
        out["rating"] = float(m.group(1))
    m = re.search(r"Total reviews:\s*([\d,]+)", md)
    if m:
        out["reviews"] = int(m.group(1).replace(",", ""))

    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: ikea_extract.py <cache.md> [url]", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as fh:
        md = fh.read()
    url = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(parse(md, url), indent=2, ensure_ascii=False))
