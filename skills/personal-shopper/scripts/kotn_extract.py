#!/usr/bin/env python3
"""
Kotn (CA) product extractor — pure urllib, runs VPS-side, NO bot wall.
Verified 2026-08-23.

Kotn (kotn.com) is a custom Next.js/Vercel storefront in front of a headless
Shopify store (kotn-ss15.myshopify.com). Two data sources, both open:

  1. The PDP HTML embeds a `<script id="__NEXT_DATA__">` JSON blob carrying the
     Sanity-CMS product: title, priceRange, previewImageUrl, options
     (Colour/Size), the Shopify product id, and — critically for the
     natural-fibre gate — the "Fabric & Care" detail section with composition
     ("100% Cotton" / "100% Egyptian cotton"). Kotn is essentially all
     long-staple / organic cotton, so it's a top natural-fibre source.
  2. Live PER-SIZE stock is NOT in the SSR blob. It comes from the public
     Shopify Storefront GraphQL API:
        POST https://kotn-ss15.myshopify.com/api/2023-01/graphql.json
        header: X-Shopify-Storefront-Access-Token: <token>
     The token is a public storefront token baked into the site's JS bundle
     (pages/_app chunk: `access_token:"..."`). Re-scrape it if it rotates:
        grep -oE 'access_token:"[a-f0-9]{32}"' <the _app chunk>
     Query the product by its GID (gid://shopify/Product/<id>) — the
     myshopify *handle* differs from the kotn.com slug, so query by GID, not
     handle. quantityAvailable + availableForSale come back per variant.

USAGE:
    python3 kotn_extract.py https://kotn.com/products/mens-relaxed-check-shirt [more URLs...]

OUTPUT (per URL, JSON):
    {url, title, shopify_gid, price, currency, composition, natural_pct,
     image, colors[], sizes[{size, price, quantity, in_stock}], any_in_stock}

Notes:
- Natural fibres counted: cotton, wool, linen, silk, cashmere, hemp, jute,
  ramie, alpaca, mohair, lyocell/tencel (plant-derived). Viscose/rayon/modal
  count as SYNTHETIC per the skill's fibre rule.
- If the GraphQL call fails (token rotated), price still comes from SSR; stock
  is reported null. Re-derive the token per the note above.
"""
import sys, re, json, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
GQL_URL = "https://kotn-ss15.myshopify.com/api/2023-01/graphql.json"
STOREFRONT_TOKEN = "bf270532d43fe486e0585779d2c8ae7d"  # public; re-scrape if rotated

NATURAL = ("cotton", "wool", "linen", "silk", "cashmere", "hemp", "jute",
           "ramie", "alpaca", "mohair", "lyocell", "tencel", "merino")


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _flatten(blocks):
    """Sanity portable-text -> list of plain strings."""
    out = []
    for b in blocks or []:
        if isinstance(b, dict) and b.get("_type") == "block":
            out.append("".join(c.get("text", "") for c in b.get("children", [])))
    return out


def natural_pct(comp):
    """Sum natural-fibre percentages from a composition string like '80% Cotton, 20% Polyester'."""
    if not comp:
        return None
    pairs = re.findall(r"(\d+)\s*%\s*([A-Za-z][A-Za-z /-]*)", comp)
    if not pairs:
        # No explicit %; if it names only natural fibres and says nothing synthetic, treat 100
        low = comp.lower()
        if any(n in low for n in NATURAL) and "100%" in low:
            return 100
        if any(n in low for n in NATURAL):
            return 100  # Kotn descriptions like "Made from 100% Egyptian cotton"
        return None
    total = 0
    for pct, fib in pairs:
        if any(n in fib.lower() for n in NATURAL):
            total += int(pct)
    return total


def parse_next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  html, re.S)
    if not m:
        return None
    d = json.loads(m.group(1))
    pp = d["props"]["pageProps"]
    p = pp["product"]
    gid = pp.get("shopifyProductID")
    store = (p.get("shopifyProducts") or [{}])[0].get("productReferenceV2", {}).get("store", {})
    # SSR priceRange.minVariantPrice is a bare number (e.g. 158), NOT a {amount,currencyCode} dict
    price = store.get("priceRange", {}).get("minVariantPrice")
    image = store.get("previewImageUrl")
    colors, sizes = [], []
    for o in store.get("options", []):
        if o.get("name", "").lower() == "colour":
            colors = o.get("values", [])
        elif o.get("name", "").lower() == "size":
            sizes = o.get("values", [])
    # composition from the "Fabric & Care" detail section
    comp = None
    for s in p.get("details", []):
        if isinstance(s, dict) and s.get("detailTitle", "").lower().startswith("fabric"):
            lines = _flatten(s.get("detailContent", []))
            # pick the line that mentions a fibre / %
            for ln in lines:
                if re.search(r"%|" + "|".join(NATURAL), ln, re.I) and "wash" not in ln.lower():
                    comp = ln.strip()
                    break
    return {"title": p.get("title"), "shopify_gid": gid, "price": price,
            "image": image, "colors": colors, "sizes": sizes, "composition": comp}


def fetch_stock(gid):
    """Per-size live stock via Shopify Storefront GraphQL. gid = numeric product id."""
    query = ('{ node(id: "gid://shopify/Product/%s") { ... on Product { '
             'availableForSale variants(first: 100) { edges { node { '
             'availableForSale quantityAvailable price { amount currencyCode } '
             'selectedOptions { name value } } } } } } }') % gid
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(GQL_URL, data=body, headers={
        "User-Agent": UA, "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Shopify-Storefront-Access-Token": STOREFRONT_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError):
        return None
    node = (j.get("data") or {}).get("node")
    if not node:
        return None
    out = []
    for e in node.get("variants", {}).get("edges", []):
        n = e["node"]
        opts = {o["name"]: o["value"] for o in n.get("selectedOptions", [])}
        out.append({"size": opts.get("Size"), "colour": opts.get("Colour"),
                    "price": float(n["price"]["amount"]),
                    "currency": n["price"].get("currencyCode"),
                    "quantity": n.get("quantityAvailable"),
                    "in_stock": bool(n.get("availableForSale"))})
    return out


def extract(url):
    html = _get(url)
    nd = parse_next_data(html)
    if not nd:
        return {"url": url, "error": "no __NEXT_DATA__"}
    stock = fetch_stock(nd["shopify_gid"]) if nd.get("shopify_gid") else None
    price = nd.get("price")  # bare number from SSR (CAD)
    sizes = []
    currency = "CAD"
    if stock:
        currency = stock[0].get("currency") or currency
        for v in stock:
            sizes.append({"size": v["size"], "price": v["price"],
                          "quantity": v["quantity"], "in_stock": v["in_stock"]})
    else:
        for s in nd.get("sizes", []):
            sizes.append({"size": s, "price": price,
                          "quantity": None, "in_stock": None})
    return {
        "url": url,
        "title": nd["title"],
        "shopify_gid": nd["shopify_gid"],
        "price": price,
        "currency": currency,
        "composition": nd["composition"],
        "natural_pct": natural_pct(nd["composition"]),
        "image": nd["image"],
        "colors": nd["colors"],
        "sizes": sizes,
        "any_in_stock": any(s["in_stock"] for s in sizes) if stock else None,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    results = [extract(u) for u in sys.argv[1:]]
    print(json.dumps(results, indent=2, ensure_ascii=False))
