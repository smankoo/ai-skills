"""Amazon.ca search + product-page extractor, run INSIDE browser_exec (VPS browser, signed-in session).

Usage (inside a browser_exec call, with your own session name):

    exec(open('~/.hermes/skills/sumeet/personal-shopper/scripts/amazon_extract.py').read())
    print(amazon_search('rolled oats', limit=10))          # organic results only (sponsored dropped)
    print(amazon_pdp('B07J3DC7YB'))                        # one product page
    print(amazon_variants('B0XXXXXXXX', want={'size': 'M'}, max_children=3))  # apparel: parent -> child ASIN pages

Requires the browser_exec helpers (goto_url, wait_for_load, js) to be in scope and the two
JS extractors next to this file: amazon_search.js, amazon_pdp.js. Python stdlib only.
READ ONLY: it navigates and reads. It never clicks Add to Cart / Buy Now / Subscribe & Save.
Verified 2026-10-08 on amazon.ca with a Burlington L7M 0K5 delivery address.
"""
import json, os, time, re, urllib.parse

# exec() inside browser_exec inherits the harness's __file__, so don't trust it: use an explicit dir.
_DIR = os.environ.get('AMAZON_JS_DIR', os.path.expanduser('~/.hermes/skills/sumeet/personal-shopper/scripts'))
_SEARCH_JS = open(os.path.join(_DIR, 'amazon_search.js')).read()
_PDP_JS = open(os.path.join(_DIR, 'amazon_pdp.js')).read()


def _poll(src, tries=8, delay=1.5):
    res = None
    for _ in range(tries):
        try:
            res = js(src)
        except Exception as e:  # page mid-navigation
            res = {'ready': False, 'err': str(e)[:120]}
        if isinstance(res, dict) and res.get('ready'):
            return res
        time.sleep(delay)
    return res


def amazon_search(query, limit=20, extra=''):
    """extra: raw URL params, e.g. '&rh=p_85:5690392011' (Prime) or '&s=price-asc-rank'."""
    goto_url('https://www.amazon.ca/s?k=' + urllib.parse.quote_plus(query) + extra)
    wait_for_load()
    r = _poll(_SEARCH_JS)
    if isinstance(r, dict) and r.get('results'):
        r['results'] = r['results'][:limit]
    return r


def amazon_pdp(asin_or_url):
    url = asin_or_url if asin_or_url.startswith('http') else 'https://www.amazon.ca/dp/' + asin_or_url
    goto_url(url)
    wait_for_load()
    r = _poll(_PDP_JS)
    if isinstance(r, dict) and r.get('variants') and len(json.dumps(r['variants'])) > 4000:
        # keep output small: summarise big variant maps
        v = r['variants']
        v['by_asin_sample'] = dict(list(v['by_asin'].items())[:12])
        v.pop('by_asin')
    return r


def amazon_variants(parent, want=None, max_children=3, gap_s=2.0):
    """Load the parent PDP, read dimensionValuesDisplayData (child ASIN -> [dim values]), then load up to
    max_children child ASIN pages whose values contain every string in want.values() (case-insensitive).
    want example: {'size': 'Medium', 'colour': 'Black'}. Returns {'parent':..., 'children':[pdp...]}."""
    goto_url('https://www.amazon.ca/dp/' + parent)
    wait_for_load()
    p = _poll(_PDP_JS)
    by = ((p or {}).get('variants') or {}).get('by_asin') or {}
    wants = [w.lower() for w in (want or {}).values()]
    def ok(vals):
        vs = [str(x).lower() for x in vals]
        return all(any(w == x or w in x.split() for x in vs) for w in wants)
    picks = [a for a, vals in by.items() if ok(vals)][:max_children]
    kids = []
    for a in picks:
        time.sleep(gap_s)
        c = amazon_pdp(a)
        if isinstance(c, dict):
            c.pop('variants', None)
            c['dims'] = by.get(a)
        kids.append(c)
    return {'parent': {k: (p or {}).get(k) for k in ('asin', 'title', 'price', 'image')},
            'dims': ((p or {}).get('variants') or {}).get('dims'), 'n_children': len(by),
            'matched': picks, 'children': kids}
