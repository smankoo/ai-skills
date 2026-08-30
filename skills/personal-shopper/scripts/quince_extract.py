#!/usr/bin/env python3
"""
Quince (CA) product extractor — personal-shopper skill.

Quince (quince.com) is a DTC "affordable luxury" brand and one of the strongest
natural-fibre sources available: deep 100% organic-cotton, Mongolian cashmere,
European linen, mulberry silk, and merino lines (women / men / kids / home).

NO BOT WALL from the VPS: a plain urllib GET of the Canadian PDP returns the full
static HTML with everything the skill needs. Two data blocks carry it:

  1. JSON-LD `@graph` -> ProductGroup.hasVariant[]  (one entry per colour x size)
     gives per-variant: price, priceCurrency (CAD on /ca/), availability
     (InStock/OutOfStock), image, sku, colour, size.  <-- price + stock + image
  2. __NEXT_DATA__  props.pageProps.pageData.context.pageDataJson.product
     gives the EXACT fibre composition in `details` (an <ul><li>Made from 55%
     linen, 45% cotton...</li></ul>) and the loose `material` label. The JSON-LD
     `material` is only a marketing label ("Organic Cotton") — for the fibre gate
     read `details`, which states the real percentages.

IMPORTANT for the natural-fibre rule:
  - Quince product NAMES lie by omission ("Cotton Modal ... Tee" is a blend;
    modal is semi-synthetic -> counts as synthetic). ALWAYS read the % from
    `details`, never trust the title or the `material` label.
  - modal / viscose / rayon / lyocell / tencel / elastane / spandex / nylon /
    polyester / acrylic count as SYNTHETIC here (lyocell is plant-derived but we
    follow the skill's default of counting viscose-family as synthetic).

USAGE
  # 1. fetch the Canadian PDP (no special headers needed; /ca/ gives CAD):
  UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
  curl -s -A "$UA" "https://www.quince.com/ca/women/<handle>" -o page.html
  # 2. parse:
  python3 quince_extract.py page.html
  #    (or pass a URL directly and it will fetch with urllib)

OUTPUT (per product), JSON:
  {url, name, material_label, composition, natural_pct, image, currency,
   price_min, price_max, colors[], sizes[], variants:[{color,size,price,
   availability,sku}], any_in_stock, rating, review_count}

Verified 2026-08-30 on three live /ca/ products:
  - 100-organic-cotton-sweater-tee     -> "Made from 100% organic cotton", natural 100, $55 CAD, 25/25 InStock
  - lightweight-cotton-cashmere-relaxed-sweater-tee -> cotton+cashmere blend (natural)
  - tees/cotton-modal-crew-neck-tee     -> cotton+modal blend, modal = synthetic
"""
import sys, re, json, html as _html
import urllib.request

NATURAL = ('cotton', 'wool', 'linen', 'cashmere', 'silk', 'merino', 'alpaca',
           'hemp', 'mohair', 'ramie', 'jute')
# viscose/rayon/modal/lyocell/tencel treated as synthetic per skill default.
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA,
                                               'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def _jsonld_graph(page):
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                         page, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(j, dict) and '@graph' in j:
            return j['@graph']
    return []


def _next_data(page):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  page, re.S)
    return json.loads(m.group(1)) if m else None


def _composition_from_details(details_html):
    """Pull the fibre line out of the `details` <ul><li>...</li></ul> HTML.
    Returns (composition_string, natural_pct) or (None, None)."""
    if not details_html:
        return None, None
    text = _html.unescape(re.sub(r'<[^>]+>', ' ', details_html))
    # find every "NN% fibre" token
    pairs = re.findall(r'(\d{1,3})\s*%\s*(organic\s+)?([a-zA-Z]+)', text)
    if not pairs:
        return None, None
    natural = 0
    parts = []
    for pct, _org, fib in pairs:
        pct = int(pct)
        fib_l = fib.lower()
        parts.append(f"{pct}% {fib}")
        if any(fib_l.startswith(n) for n in NATURAL):
            natural += pct
    comp = ', '.join(parts)
    return comp, natural


def parse(page, url=None):
    graph = _jsonld_graph(page)
    pg = next((g for g in graph if g.get('@type') == 'ProductGroup'), None)
    if pg is None:
        pg = next((g for g in graph if g.get('@type') == 'Product'), None)
    nd = _next_data(page)
    prod = None
    if nd:
        try:
            prod = nd['props']['pageProps']['pageData']['context']['pageDataJson']['product']
        except Exception:
            prod = None

    name = (pg or {}).get('name') or (prod or {}).get('title')
    material_label = (pg or {}).get('material') or (prod or {}).get('material')

    # exact composition from __NEXT_DATA__ details HTML
    composition, natural_pct = (None, None)
    if prod:
        composition, natural_pct = _composition_from_details(prod.get('details'))
    if composition is None and material_label:
        # fall back to loose label -> assume 100% if it names a single natural fibre
        composition = material_label

    variants, prices, colors, sizes = [], [], [], []
    currency = None
    image = None
    rating = review_count = None
    for v in (pg or {}).get('hasVariant', []):
        off = v.get('offers') or {}
        if isinstance(off, list):
            off = off[0] if off else {}
        price = off.get('price')
        avail = str(off.get('availability', '')).rsplit('/', 1)[-1]
        currency = currency or off.get('priceCurrency')
        img = v.get('image')
        if isinstance(img, list):
            img = img[0] if img else None
        image = image or img
        col, sz = v.get('color'), v.get('size')
        if col and col not in colors:
            colors.append(col)
        if sz and sz not in sizes:
            sizes.append(sz)
        if price:
            try:
                prices.append(float(price))
            except ValueError:
                pass
        variants.append({'color': col, 'size': sz, 'price': price,
                         'availability': avail, 'sku': v.get('sku')})
        ar = v.get('aggregateRating')
        if ar and rating is None:
            rating = ar.get('ratingValue')
            review_count = ar.get('reviewCount')

    any_in_stock = any(v['availability'] == 'InStock' for v in variants)
    return {
        'url': url or (pg or {}).get('offers', {}) and url,
        'name': name,
        'material_label': material_label,
        'composition': composition,
        'natural_pct': natural_pct,
        'image': image,
        'currency': currency,
        'price_min': min(prices) if prices else None,
        'price_max': max(prices) if prices else None,
        'colors': colors,
        'sizes': sizes,
        'variants': variants,
        'any_in_stock': any_in_stock,
        'rating': rating,
        'review_count': review_count,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    arg = sys.argv[1]
    if arg.startswith('http'):
        page = fetch(arg)
        url = arg
    else:
        page = open(arg, encoding='utf-8', errors='replace').read()
        url = sys.argv[2] if len(sys.argv) > 2 else None
    out = parse(page, url)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
