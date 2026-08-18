#!/usr/bin/env python3
"""
Roots (roots.com) product extractor — VPS-side, pure urllib. No bot wall.

Roots CA/US runs on Salesforce Commerce Cloud (Demandware). The PDP HTML is
fully server-rendered, so a plain curl/urllib GET returns everything the
personal-shopper skill needs — NO exit node, NO Mac CDP delegation.

Rung that works: JSON-LD `Product` (name/price/availability/image/sku) +
static PDP HTML for composition and per-size/per-colour stock. Verified 2026-08-17.

Usage:
    python3 roots_extract.py "https://www.roots.com/ca/en/<slug>-<styleid>.html" [more urls...]

Output (per URL), JSON to stdout:
    {url, style, name, price, currency, availability, composition, natural_pct,
     image, colors:[{name,code,in_stock}], sizes:[{size,in_stock}], any_size_in_stock}

Notes:
- Product URL shape: https://www.roots.com/ca/en/<slug>-<styleid>.html
  (US locale is /us/en/...). Find candidates via
  web_search "site:roots.com <category> <keyword>".
- Composition line lives under "<strong>Fibre Content</strong><br> ...".
  Roots labels "recycled polyester" as such -> count as SYNTHETIC. "organic
  cotton" is still cotton -> NATURAL.
- Per-size stock reflects the DEFAULT/selected colour: <span data-attr-value="M"
  class="size-value ... selectable|unselectable">. Colours use the same
  selectable/unselectable on `color-value` swatches (data-attr-name = colour).
"""
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

NATURAL = re.compile(r'cotton|wool|linen|silk|cashmere|lyocell|tencel|hemp|jute|ramie', re.I)
SYNTH = re.compile(r'polyester|nylon|acrylic|elastane|spandex|viscose|rayon|modal|polyamide', re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def natural_pct(comp):
    """Sum natural-fibre percentages from a composition string."""
    if not comp:
        return None
    total = 0
    for pct, name in re.findall(r'(\d{1,3})\s*%\s*([a-zA-Z ]+)', comp):
        seg = name.strip()
        if NATURAL.search(seg) and not SYNTH.search(seg):
            total += int(pct)
    return total


def parse(html, url):
    out = {"url": url, "style": None, "name": None, "price": None,
           "currency": None, "availability": None, "composition": None,
           "natural_pct": None, "image": None, "colors": [], "sizes": [],
           "any_size_in_stock": None}

    m = re.search(r'-(\d{6,})\.html', url)
    if m:
        out["style"] = m.group(1)

    # JSON-LD Product
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(block)
        except Exception:
            continue
        if j.get("@type") == "Product":
            out["name"] = j.get("name")
            out["style"] = out["style"] or j.get("sku") or j.get("mpn")
            img = j.get("image")
            out["image"] = img[0] if isinstance(img, list) and img else img
            o = j.get("offers") or {}
            if isinstance(o, list):
                o = o[0] if o else {}
            out["price"] = o.get("price")
            out["currency"] = o.get("priceCurrency")
            out["availability"] = re.sub(r'https?://schema\.org/', '', str(o.get("availability") or ''))
            break

    # Composition line lives in the details tab under a bold label that varies by
    # department: adults use "<strong>Fibre Content</strong><br> 80% organic cotton...",
    # kids use "<strong>ABOUT</strong><br />80% organic cotton...". Match either label,
    # tolerate <br> / <br /> and an optional "Solid colours:" prefix.
    m = re.search(r'<strong>\s*(?:Fibre Content|About)\s*</strong>\s*<br\s*/?>\s*([^<]+)', html, re.I)
    if m:
        out["composition"] = re.sub(r'\s+', ' ', m.group(1)).strip().rstrip('.')
        out["natural_pct"] = natural_pct(out["composition"])

    # Colours: color-value swatches
    for sp in re.findall(r'<span[^>]*class="[^"]*color-value[^"]*"[^>]*>', html):
        code = (re.search(r'data-attr-value="([^"]*)"', sp) or [None, None])[1]
        cls = (re.search(r'class="([^"]*)"', sp) or [None, ""])[1]
        instock = 'selectable' in cls and 'unselectable' not in cls
        # colour name lives on the same tag or a sibling data-attr-name; try both
        name = (re.search(r'data-attr-name="([^"]*)"', sp) or [None, None])[1]
        if code:
            out["colors"].append({"code": code, "name": name, "in_stock": instock})

    # Sizes: size-value swatches (reflect the default/selected colour)
    for sp in re.findall(r'<span[^>]*class="[^"]*size-value[^"]*"[^>]*>', html):
        val = (re.search(r'data-attr-value="([^"]*)"', sp) or [None, None])[1]
        cls = (re.search(r'class="([^"]*)"', sp) or [None, ""])[1]
        instock = 'selectable' in cls and 'unselectable' not in cls
        if val:
            out["sizes"].append({"size": val, "in_stock": instock})

    out["any_size_in_stock"] = any(s["in_stock"] for s in out["sizes"]) if out["sizes"] else None
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: roots_extract.py <product-url> [...]", file=sys.stderr)
        sys.exit(1)
    results = [parse(fetch(u), u) for u in sys.argv[1:]]
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
