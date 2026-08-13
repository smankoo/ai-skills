# Retailer recipes

Working extraction snippets and every failure mode hit so far. Verified 2026-08-04.

These are the Canadian retailers used in the runs so far — they're **recipes, not
recommendations**. Nothing here says the user shops at these stores. Use whatever retailers suit the
user's country, budget, and stated habits, and add a recipe when you work out a new one. The "Rules
that apply everywhere" section below is the part that transfers to any site.

All of these run through the browser MCP:
`mcp__browser__browser_execute_js`, `browser_navigate`, `browser_new_tab`, `browser_list_tabs`.

> **This file is meant to grow.** Every run that touches a new site, or finds an old recipe stale,
> should leave an edit here — see SKILL.md §12. Working out how a retailer behaves is the expensive
> part of a run and the cheapest thing to write down. Record mechanics only: selectors, URL shapes,
> failure modes. Never a person's name, size, budget, or order.

## Adding a retailer — the shape to follow

Copy this. A recipe earns its place by being specific enough to paste and run.

````markdown
## <Retailer> — <the trick that makes it work>

<Country/segment, one line: which market and price level it serves.>
<How to get name, price, availability, image — the actual method.>

```js
// A snippet that ran and worked.
```

**Selectors** (verified YYYY-MM-DD)
| What | Selector |
|---|---|
| Title | `#productTitle` |

**Failure modes**
- <What broke, and the workaround. This is the highest-value part.>
- <Dead ends: what cannot work, so nobody retries it.>
````

Date-stamp selectors — sites change, and a reader needs to know whether to trust or re-verify. When a
note turns out to be true of every site, promote it to the section below and delete the copies.

## Rules that apply everywhere

1. **One tab per origin.** Cross-origin `fetch()` fails with "Failed to fetch". Keep a
   long-lived tab per retailer and run `fetch()` from within it.
2. **Page-scoped helpers die on navigation.** `window.__V` / `window.__G` vanish on every
   navigate and you get "JS error: Uncaught". Redefine after each one.
3. **Verify per size, not per product.** A product on the category grid says nothing about
   whether it exists in the size you need.
4. **A suspiciously low price is usually sold-out clearance.** Everything at `$9.99` means gone,
   not bargain. Always read availability alongside price.
5. **Never let multiple subagents share one browser.** They deadlock in sleep-retry loops
   ("the browser tool has been down for ~10 minutes"). Drive it yourself, or give agents
   disjoint short jobs. If they stall, parse their JSONL under the session dir to salvage
   verified products instead of re-running.
6. **Try `web_extract` before heavier tooling.** As of 2026-08, `web_extract` runs a real
   headless browser (self-hosted Crawl4AI) — it executes JavaScript and returns fully-rendered
   page markdown, not the empty curl shell. It costs nothing (local) and needs no browser session.
   Use it as the CHEAP FIRST PASS: it's enough when the fields you need are in the rendered HTML,
   especially a `<script type="application/ld+json">` block (parse `offers.price`, `availability`,
   `name`, `image`) or visible price/title text. It is NOT enough when the data loads from a
   *separate* XHR or hides behind a click (accordion/tab) — plain `web_extract` won't click or
   intercept. In that case escalate to the public-JSON-API / Shopify-JSON / CDP path. Rough ladder
   per retailer: **web_extract (JSON-LD + visible fields) → public/undocumented JSON API →
   Shopify JSON → CDP/browser interaction**. Record in the recipe which rung actually worked.

## Uniqlo (CA) — public JSON API, the best natural-fibre source found so far

Canada, mid-market. **This is the highest-leverage retailer for a natural-fibre rule** — deep
cotton/wool/linen/cashmere lines (Supima, oxford, flannel, merino, lambswool, corduroy, selvedge)
and, crucially, a clean public JSON API that returns **live fibre composition, price, stock, image,
and country of origin** without scraping the DOM. No bot wall on the API. Verified 2026-08-13.

The only trick: every call needs the header **`x-fr-clientid: uq.ca.web-spa`** (plus
`x-fr-client-version` and `accept: application/json`). Discover the exact clientid live from
DevTools/network if it rotates — it's sent on every XHR the site makes. Run `fetch()` from an
already-loaded `uniqlo.com` tab (one tab per origin rule applies).

Base: `https://www.uniqlo.com/ca/api/commerce/v5/en`

- **Keyword search** (find candidates): `GET /products?q=<terms>&limit=20&offset=0&httpFailure=true`
  → `result.items[]` with `productId` (E-number like `E456630-000`), `name`, `genderCategory`,
  `prices.base.value`, `images`.
- **Product detail** (the money endpoint — composition + stock): `GET /products/<E-id>?httpFailure=true`
  → returns `result.name`, `l2s`/variants, and a **`composition`** array (e.g. `[{fabric:"COTTON",
  percentage:100}]`) plus `origin`. Sum the natural fibres (cotton/wool/linen/silk/cashmere/lyocell*)
  and gate at the user's threshold. *(lyocell/Tencel is plant-derived; count it natural unless told
  otherwise — a barrel jean at 79% cotton / 21% lyocell passes a 70% rule.)*
- **Stock**: variant objects carry a stock/availability flag; a fully OOS product returns no buyable
  l2s. Verify before recommending — several picks (corduroy jacket/barrel pants) were OOS while
  cotton substitutes were in stock.

```js
const H = {'accept':'application/json','Content-Type':'application/json',
           'x-fr-client-version':'3.2612.10','x-fr-clientid':'uq.ca.web-spa'};
// composition + price for one product
const r = await fetch(`https://www.uniqlo.com/ca/api/commerce/v5/en/products/E456630-000?httpFailure=true`,{headers:H});
const j = await r.json();
// j.result.composition -> [{fabric:'COTTON', percentage:100}], j.result.prices...
```

**Product page URL** (for the email link): `https://www.uniqlo.com/ca/en/products/<E-id>` —
resolves to the live PDP (redirects to append colour/size codes). Verified good 2026-08-13.

**Image URL** pattern: `https://image.uniqlo.com/UQ/ST3/ca/imagesgoods/<6-digit>/item/cagoods_<NN>_<6-digit>_3x4.jpg`
(the 6-digit is the E-number without the `E`/`-000`). Some goods use the `WesternCommon` path
instead of `ca`: `.../ST3/WesternCommon/imagesgoods/<id>/item/goods_<NN>_<id>_3x4.jpg`. Grab the real
`images` array from the search/detail JSON rather than hand-building when possible.

**Failure modes**
- Missing/ wrong `x-fr-clientid` header → 403 / empty. It's mandatory on every call.
- Cross-origin `fetch()` (e.g. running it from a herschel tab) → "Failed to fetch". One tab per origin.
- AirSense blazers, fleece, "Double Face" coats, many "washable" knits, and rayon/HeatTech lines are
  **predominantly synthetic** — they fail a natural-fibre gate. Don't fall in love before reading
  `composition`. Uniqlo outerwear especially tends to blend; the 100% cotton Denim Trucker Jacket
  was the only clean outerwear option found.
- `x-fr-client-version` drifts over time; if calls start failing, refresh both header values from a
  live network capture.

## Herschel — Shopify storefront JSON (kids backpacks etc.)

Global; DTC brand. It's a Shopify store, so the standard Shopify JSON endpoints work with **no bot
wall** once a herschel.com tab is loaded (same-origin). Great for kids' bags sized by age. Verified
2026-08-13.

- **Predictive search**: `GET /search/suggest.json?q=<terms>&resources[type]=product&resources[limit]=10`
  → `resources.results.products[]` with `title`, `url`, `price`, `available`, `featured_image.url`.
- **Product detail**: `GET /products/<handle>.json` → `product.title`, `product.variants[]`
  (`title`, `price`, `available`), `product.images[].src`, and `product.body_html` — the **age range
  lives in `body_html`** (e.g. "young adventurers aged 3–7 years" vs the Youth pack "aged 8–12").
  Read it: the "Kids" and "Youth" Heritage packs look identical but are sized years apart.

```js
const r = await fetch('/products/herschel-heritage-kids-backpack.json',{headers:{'accept':'application/json'}});
const p = (await r.json()).product;  // p.variants[].price/available, p.images[0].src, p.body_html
```

**Failure modes**
- US site is `herschel.com` with `/shop/...` and `/pages/...` paths; the `/en-ca/collections/...`
  paths 404 on it. Navigating `products.json` directly can return `ERR_HTTP_RESPONSE_CODE_FAILURE` —
  fetch same-origin from a loaded page instead. The US catalog is fine for identifying the right
  product/handle; hand the user the `.ca` link for checkout.
- A sandboxed/404 error page has `location.origin === "null"` → all `fetch()` fail. Navigate to a
  real store page (e.g. `/pages/kids`) first, then fetch.

## Simons — JSON-LD

Category URLs bounce to `/en` under bot protection: `browser_navigate`, `location.assign()`, and
a fresh tab all fail. `mcp__ddg-search__fetch_content` returns 403. The reliable path is a
same-origin `fetch()` from an already-loaded simons.ca tab, then parse the
`application/ld+json` block — it carries `name`, `brand`, `offers.price`, `offers.availability`.

```js
window.__V = async (urls) => {
  const out = [];
  for (const u of urls) {
    try {
      const r = await fetch('https://www.simons.ca' + u);
      const t = await r.text();
      const m = t.match(/<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/);
      if (!m) { out.push({u, status: r.status, noLd: 1}); continue; }
      const j = JSON.parse(m[1]);
      const o = j.offers || {};
      out.push({
        u,
        name:  j.name,
        brand: (j.brand && (j.brand.name || j.brand)) || '',
        price: o.price || '',
        avail: String(o.availability || '').replace('https://schema.org/', ''),
      });
    } catch (e) { out.push({u, err: String(e).slice(0, 60)}); }
  }
  return out;
};
// await window.__V(['/en/men-clothing/shirts/overshirts/utility-overshirt--16126-2500'])
```

Accept only `avail === "InStock"`. Product paths look like
`/en/<dept>/<cat>/<subcat>/<slug>--<id1>-<id2>`. House brands: **Le 31** (men),
**Twik** (younger women), **Contemporaine** and **Icône** (women).

Colours are *not* in the JSON-LD reliably — infer from the product name and tell the user to
glance at the photo before adding to cart.

## Gap / Old Navy — per-size stock

Both share the Gap Canada platform, so one recipe covers both. A size is **out of stock** when
its `<label for="pdp_buybox_dimension_…">` carries `fds_selector__label--unavailable`.

```js
window.__G = async (pids, want) => {
  const out = [];
  for (const pid of pids) {
    try {
      const r = await fetch('/browse/product.do?pid=' + pid + '&vid=1');
      const t = await r.text();
      const nm = (t.match(/<h1[^>]*>([\s\S]{2,120}?)<\/h1>/) || [])[1] || '';
      const pr = [...t.matchAll(/CA\$(\d+\.\d\d)/g)].map(m => m[1]).slice(0, 3);
      const labels = [...t.matchAll(/<label for="pdp_buybox_dimension_([^"]+)"[\s\S]{0,400}?class="([^"]*?)"/g)]
        .map(m => ({size: m[1], oos: /--unavailable/.test(m[2])}));
      const hit = labels.filter(l => want.some(w => l.size.trim() === w));
      out.push({
        pid,
        name: nm.replace(/<[^>]+>/g, '').trim().slice(0, 70),
        prices: pr,
        want: hit.map(h => h.size + (h.oos ? ':OOS' : ':OK')),
      });
    } catch (e) { out.push({pid, err: String(e).slice(0, 50)}); }
  }
  return out;
};
// await window.__G(['490929033','422209023'], ['18-24M','5 YRS'])
```

Run it from a tab on the matching origin: `www.gapcanada.ca` or `oldnavy.gapcanada.ca`.
An empty `want` array means the size isn't offered at all — treat as OOS.

Product URL: `https://<origin>/browse/product.do?pid=<pid>&vid=1`

### Category IDs (verified working)

Browse with `/browse/category.do?cid=<id>`. Many guessed IDs return empty grids or the wrong
department — when in doubt, scrape nav links off a known-good page rather than guessing.

**Old Navy, toddler boy**

| cid | Category |
|---|---|
| 1127055 | Bottoms |
| 3034099 | T-shirts |
| 1044462 | Sweatshirts |
| 62291 | Sweaters |
| 53862 | Coats & jackets |
| 34722 | Pyjamas |
| 13130 | Socks & underwear |

**Gap, baby & toddler boy**

| cid | Category |
|---|---|
| 1016169 | Shirts |
| 3024164 | Polos |
| 1016106 | Pants |
| 1016096 | T-shirts |
| 1016107 | Sweatshirts |
| 1175810 | Toddler-boy sweaters |
| 1108608 | Baby coats |

Known-bad: Old Navy `1044461`, `1044465`, `1044466` (empty); Gap `1016099`, `1016097` (empty),
`5745` (returns womenswear).

## Size charts

**Gap kids, by height**

| Size | Height |
|---|---|
| 12-18M | 74–79 cm |
| 18-24M | 79–84 cm |
| 4 YRS | 39–42 in |
| 5 YRS | 42–45 in |

Bands are inclusive at the top, so a child measuring exactly 79 cm is at the *ceiling* of
12-18M and should go up.

**Toddler shoes (US "C"), by foot length**

| cm | Size |
|---|---|
| 12.7 | 5C |
| 13.0 | 5.5C |
| 13.3 | 6C |
| 13.8 | 6.5C |
| 14.2 | 7C |
| 16.9 | 10.5C |
| 17.3 | 11C |
| 17.6 | 11.5C |
| 17.9 | 12C |

Sanity check: **US 4C ≈ 12.0 cm is an ~18-month-old's shoe.** If a stored shoe size for a
4-year-old reads "4", it's wrong.

## Sale timing

Old Navy runs ~50% off frequently — it's why two children's wardrobes come in under $850. Say
when pricing looks promotional and won't hold. Conversely, big-ticket adult outerwear (Barbour
and similar) goes on sale in November, so it can wait.

## Colour diversity — a curation rule (learned 2026-08-08)

A harvest that ignores colour converges on one colour (whatever the retailer photographs most —
usually navy/black), and the resulting cart reads as a uniform. Two-part fix:

1. **Harvest**: record the default variant's actual colour per product, plus available colourways,
   in a `colors` field. JSON-LD usually lacks colour — read it off the PDP or infer from the
   product name/slug.
2. **Curate**: before finalizing, tally colours across the whole cart. No colour should exceed
   ~30% of items; the stated palette should all be represented. Where a piece comes in multiple
   colourways, name the specific colour to buy in the item's `meta` line.
