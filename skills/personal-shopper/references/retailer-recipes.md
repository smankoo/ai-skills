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

## The Children's Place (CA) — rendered-DOM via web_extract (no JSON-LD, no API)

Canada, cheap/resilient kids' chain — a natural workhorse-clothes store (uniform polos,
basic tees, joggers, PJs) in the "kids, play clothes" role. Confirmed in Sumeet's YNAB
history. Domain is **`childrensplace.com/ca`** (NOT `childrensplace.ca`). Sister brand
Gymboree shares the platform (`gymboree.com/ca`) — the recipe should transfer.

**Which rung worked: `web_extract` (rendered DOM) — rung 4.** No usable `application/ld+json`
block, and no clean public JSON API was found. But the JS-rendered markdown that `web_extract`
returns carries **everything** the skill needs: title, sale + original price, % off, fabric
composition (the `FABRICATION:` line — critical for the natural-fibre gate), colour swatches,
Cloudinary image URL, and item number. Parse it with
`scripts/childrensplace_extract.py`. Verified 2026-08-15 on two live products
(cotton polo `1124756_NJ`, polyester PJs `3058635_IV`) — prices, %off, and composition
matched the live pages exactly.

**Product URL shape:** `https://www.childrensplace.com/ca/p/<Slug-Words>-<productId>-<colorCode>`
e.g. `.../p/Boys-Uniform-Short-Sleeve-Pique-Polo-1124756-NJ`. The `Item #: <productId>_<colorCode>`
line at the bottom of the page is the authoritative id. Find candidate URLs via
`web_search "childrensplace.com/ca <category> <keyword>"` — search result snippets even carry
the `FABRICATION:` line sometimes.

```bash
# 1. Render the PDP (retry on Akamai — see failure modes):
#    web_extract(urls=["https://www.childrensplace.com/ca/p/<slug>-<id>-<color>"])
#    -> saves full page to ~/.hermes/cache/web/<host>-<hash>.md
# 2. Parse it:
python3 scripts/childrensplace_extract.py ~/.hermes/cache/web/www.childrensplace.com-XXXX.md
#    -> {title, sale_price, original_price, pct_off, final_sale, composition,
#        natural_pct, sizes[], colors[], image, item_no, url}
```

**Key fields (verified 2026-08-15)**
| What | Where in rendered markdown |
|---|---|
| Composition | `FABRICATION: 100% cotton pique, imported` (in Product Description) |
| Sale price | `Sale Price: $11` / `$11.00` |
| Original price | `Original Price: $16.95` |
| % off | runs into the price: `$16.9535% OFF` → parse `\.\d\d(\d{1,2})% OFF` |
| Sizes | under the `Size:` header: `XS (4)`, `S (5/6)`, `M (7/8)`, `L (10/12)`, `XL (14)`, `XXL (16)` |
| Per-size stock | `ADD TO BAG` (in stock) vs `OUT OF STOCK` after each size — **partial only, see below** |
| Colours | swatch alt-text lines: `NAUTICO![NAUTICO](...swatch...)` |
| Image | `https://assets.theplace.com/image/upload/.../ecom/assets/products/tcp/<id>/<id>_<color>.(jpg|png)` |
| Volume price | `GET 6+ FOR $8 EACH` (multi-buy — surface it if buying ×N) |
| Flame/safety | PJs carry `flame resistant` + OEKO-TEX note; PJs are usually 100% polyester (fail natural gate) |

**Failure modes**
- **Akamai intermittently blocks web_extract** → `"Blocked by anti-bot protection: Akamai block"`.
  It is NOT a hard wall and NOT press-and-hold — just **retry the same URL**; a 2nd/3rd call renders
  clean (one of two URLs blocked on first pass, succeeded on retry, 2026-08-15). No exit node or Mac
  delegation needed.
- **A `FEATURED PRODUCTS` nav block renders BEFORE the real product** and carries its OWN
  prices/images/%OFF. Naïvely grabbing the first `Sale Price:`/image/`% OFF` gives the wrong
  product's data. Fix: anchor all extraction to the slice AFTER the product `# <Title>` H1
  (the parser does this via `title_pos`).
- **Per-size stock is only PARTIALLY reliable from the render.** The rendered DOM emits
  `ADD TO BAG`/`OUT OF STOCK` tokens only for the first sizes shown, so mid/large sizes come back
  `in_stock: null` (unknown). Treat `null` as "verify on the live page before recommending" — do
  NOT assume in stock. For a firm per-size answer you'd need the browser/CDP path (click the size
  swatch). Composition, price, and image are fully reliable; stock is best-effort.
- **`%OFF` is glued to the price** (`$16.9535% OFF`) — a naïve `(\d+)% OFF` grabs `9535`. Anchor on
  the two-decimal cents first: `\.\d\d(\d{1,2})% OFF`.
- No JSON-LD on the PDP; don't waste time grepping for `application/ld+json` (there isn't one).
- Domain confusion: `childrensplace.ca` is NOT the site — it's `childrensplace.com/ca`.

## Carter's / OshKosh (CA) — JSON-LD ProductGroup via CDP windowed Chrome on the Mac

Canada, cheap/resilient baby & toddler chain — the "kids, play clothes" role, and
**very natural-fibre-friendly** (huge amount of 100% cotton: bodysuits, sleepers,
pull-on pants, tees). Confirmed in Sumeet's YNAB history. CA domain is
**`cartersoshkosh.ca`** (`/en_CA/`); US is `carters.com` / `oshkosh.com` — all the
same Salesforce Commerce Cloud (Demandware) platform, so the recipe transfers. Sister
brands OshKosh B'gosh and Skip Hop share it too. Verified 2026-08-15.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3 (bot-wall bypass).**
From the VPS *every* path is walled and none is fixable VPS-side:
- `curl` / `requests` → `403 "Just a moment..."` (Cloudflare JS challenge).
- `web_extract` (Crawl4AI headless) → `"Blocked by anti-bot protection: PerimeterX block"`
  — consistent across retries (not intermittent like Akamai on Children's Place).
- The Demandware `/dw/shop/v20_4/products/...` OCAPI endpoint also 403s (Cloudflare).
It's a **passive fingerprint wall + PerimeterX**, so an exit node does NOT help — go
straight to a real windowed Chrome on the Mac over CDP (see retail-bot-wall-bypass).
`www.cartersoshkosh.ca` loaded clean over CDP with a ~13s render wait; NO interactive
press-and-hold.

**The data, once the page renders:**
- **JSON-LD `ProductGroup`** (`script[type=application/ld+json]`) is the money block.
  It carries `hasVariant[]` = one entry **per size** with `{size, sku,
  offers.price, offers.priceCurrency, offers.availability}`. This gives **per-size
  price + stock** directly (`InStock`/`OutOfStock`) — no `--unavailable` class hunt,
  no accordion clicking. Confirmed it discriminates correctly (a pants product showed
  only `NB` InStock, all other sizes OutOfStock).
- **Composition** is NOT in the JSON-LD. It lives in the description container
  `[class*=description i]` under a `Fabric & Care:` header (e.g. `100% cotton`,
  `100% cotton rib`), alongside `Imported` and an OEKO-TEX cert line. Read it from
  there. Baby basics are overwhelmingly 100% cotton → clean natural-fibre pass.
- **Image**: JSON-LD `image` (or `og:image`) — a Demandware static URL
  `.../on/demandware.static/-/Sites-carters_master_catalog/default/<hash>/productimages/<styleid>.jpg`.

**Tested extractor:** `scripts/carters_extract.py` (base64-ship to the Mac, run under
the CDP venv). Verified 2026-08-15 on two live products (`V_1L790516` 100% cotton rib,
`V_1L931210` 100% cotton) — name, image, per-size price+stock, and composition all
matched the live pages. Output per URL: `{url, name, image, currency, composition,
natural_pct, sizes:[{size,sku,price,availability}], any_in_stock}`.

**Product URL shape:** `https://www.cartersoshkosh.ca/en_CA/<slug>/V_<styleid>.html`
The `V_<8-digit>` style id is the `productGroupID` in the JSON-LD. Find candidate URLs
via `web_search "site:cartersoshkosh.ca <category> <keyword>"` (search snippets carry
direct product links).

```js
// runs in the CDP page context after ~13s render; pulls the ProductGroup + Fabric & Care
(() => {
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch(e){ return null; } }).filter(Boolean);
  const pg = lds.find(j => j['@type']==='ProductGroup') || lds.find(j => j['@type']==='Product');
  const sizes = (pg.hasVariant||[]).map(v => {
    const o = Array.isArray(v.offers)?v.offers[0]:(v.offers||{});
    return {size:v.size, sku:v.sku, price:o.price, avail:String(o.availability||'').replace('https://schema.org/','')};
  });
  const d = document.querySelector('[class*=description i]');      // "...Fabric & Care:\n100% cotton\nImported..."
  return {name:pg.name, image:Array.isArray(pg.image)?pg.image[0]:pg.image, sizes, desc:d && d.innerText};
})()
```

**Failure modes**
- Cloudflare + PerimeterX from the VPS on *every* transport (curl, web_extract, OCAPI).
  Unlike Children's Place (Akamai, retry clears it), retrying web_extract does NOT help —
  don't burn calls on it. Go to Mac CDP.
- `brand` in the JSON-LD is often `null` — it's a house brand; label it "Carter's"
  manually rather than trusting the field.
- One image per ProductGroup (the default colourway). For alternate colours you'd need
  the variant-image swap; not exposed in the top-level JSON-LD.
- Baby sizes use `NB`/`PRE`/`3M`…`24M` labels (not cm); toddler uses `2T`…`5T`. Derive
  from the child's measurement against Carter's own size chart as usual.

## Reitmans (CA) — Shopify `.js` (price/stock) + PDP-HTML accordion (composition). No bot wall.

Canada, mid-market women's (also its banners Penningtons, Addition Elle, RW&CO, Hyba —
same Shopify platform, swap the domain). **Natural-fibre-friendly**: deep 100% cotton
dress/tee lines and linen(-blend) pants. Confirmed in Sumeet's YNAB history (Priyanka).
**No bot wall from the VPS** — plain `curl`/`urllib` work, no exit node, no Mac delegation.
Verified 2026-08-16.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.**
It's a Shopify store, so the standard endpoints are open:
- **`/products/<handle>.js`** is the money endpoint: `price`/`price_min`/`price_max`
  (in **CENTS**), `compare_at_price` (original when on sale), top-level `available`, and a
  `variants[]` grid each with `option1`=colour / `option2`=size / `option3`=length,
  `price`, `compare_at_price`, and a real **`available`** boolean → **per-size/per-colour
  stock directly**. (The `.js` gives `available`; `.json` does NOT — use `.js`.)
- **Composition is NOT in the JSON** (`.js`/`.json` `description` only says e.g. "linen and
  viscose blend" in prose). The exact percentages live in the PDP **HTML**, in the
  "Materials" accordion as a single **`<li class="p3">55% Linen, 45% Viscose</li>`**. It's in
  the *static* HTML (curl gets it — no click/accordion-expand needed). Grab the lone `p3` li
  that contains a `%`.

```bash
# price/stock/image/variants (cents):
curl -s -A "$UA" "https://www.reitmans.com/products/<handle>.js"
# exact composition (MUST request text/html — see failure modes):
curl -s -A "$UA" -H 'Accept: text/html' "https://www.reitmans.com/products/<handle>" \
  | grep -oE '<li class="p3">[^<]*</li>'   # -> <li class="p3">55% Linen, 45% Viscose</li>
```

**Tested extractor:** `scripts/reitmans_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-16 on two live products:
- `wide-leg-linen-pants-women-s-collection-492032` → "55% Linen, 45% Viscose", natural_pct 55,
  $14.97 (compare $64.90), 91/250 variants in stock.
- `woven-fit-flare-midi-dress-100-cotton-498128` → "100% Cotton", natural_pct 100,
  $39.99 (compare $79.90), 7/9 in stock.
Output per URL: `{title, price, compare_at_price, on_sale, available, composition,
natural_pct, image, colors[], sizes[], lengths[], variants:[{color,size,length,price,
compare_at,available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-16)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in cents; `variants[].available`) |
| Composition (fibre %) | PDP HTML, `<li class="p3">…%…</li>` under the "Materials" accordion |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`) |
| Product URL | `https://www.reitmans.com/products/<handle>` |
| Handle | tail after `/products/`; often ends in the 6-digit style id (e.g. `-492032`) |

**Failure modes**
- **Reitmans content-negotiates on the `Accept` header.** Requesting the bare PDP URL with
  `Accept: application/json` returns the *JSON product feed*, not the HTML — so the Materials
  composition silently goes missing (`composition: None`). Send `Accept: text/html` for the
  PDP fetch, `Accept: application/json` only for `.js`/`.json`. This bit the first extractor
  run and is the single non-obvious trap here.
- `.json` lacks `available`; use `.js` for stock. `.json` is fine for `body_html`/tags only.
- Big products can have **hundreds of variants** (colour × size × length; e.g. 250) — dedup
  colours/sizes for display and rely on `available` per variant, not the top-level flag.
- **Viscose/rayon count as SYNTHETIC** per the skill's fibre rule, so a "linen blend" pant at
  55% linen / 45% viscose is natural_pct **55**, not 100 — it clears a 50% rule but fails 70%.
  Read the actual `%`, don't trust the "linen" in the title.
- Search snippets from `web_search "site:reitmans.com <keyword>"` carry the composition line and
  the `/products/<handle>` URL directly — good for discovery. A handle can go stale/renamed
  (a `.json` 404); re-derive from a fresh search.

## Tommy Hilfiger (CA) — JSON-LD `Product` + `div.content-column` composition, via CDP Chrome on the Mac

Canada, mid-market — **natural-fibre-friendly**: cotton oxfords/chinos/pique polos for adults, and
mostly cotton (often organic/regenerative) kids' tees, polos, shirts. Confirmed in Sumeet's YNAB
history. Domain **`ca.tommy.com`** (`/en/`); runs on Salesforce Commerce Cloud (Demandware). Sister
brand Calvin Klein CA is the same platform/owner (PVH) — the recipe should transfer. Verified 2026-08-17.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3 (bot-wall bypass).**
From the VPS *every* path is walled and none is fixable VPS-side:
- `curl` / `requests` → `403` (`Server: AkamaiGHost` — Akamai passive-fingerprint wall).
- `web_extract` (Crawl4AI headless) → `"Blocked by anti-bot protection: HTTP 403"` — a HARD 403,
  NOT the intermittent Akamai on Children's Place (retry does NOT clear it here).
- Demandware `/s/<site>/dw/shop/v20_4/products/...` OCAPI → 403; `.json` on the PDP path → 403.
It's a **passive** wall (no press-and-hold), so an exit node does NOT help. `ca.tommy.com` loaded
clean over CDP with a ~14s render wait; no interactive challenge.

**The data, once the page renders** (all reliable):
- **JSON-LD is a single `Product`** (NOT a `ProductGroup`), so there is **no per-size variant array**
  in it. It gives `name`, `image` (a scene7 URL), `offers.price` (the **sale/current** price),
  `offers.priceCurrency`, `offers.availability` (product-level `InStock`/`OutOfStock`), and `sku`/`mpn`
  (= the `<STYLE>-<COLOR>` code in the URL, e.g. `78JA876-WEB`).
- **Composition** lives in a leaf **`div.content-column`** whose text IS the fibre line
  (e.g. `98% organic cotton, 2% elastane.`, `100% regenerative cotton.`). NOT in the JSON-LD. Match
  generically: a childless element with `N%` + a fibre name. ("organic"/"regenerative" cotton still
  count as cotton → natural.)
- **Original price + %off**: the first `[class*=price]` element's innerText holds all of it,
  e.g. `$99.50 CAD $49.75 CAD 50% off`. The sale price = JSON-LD `offers.price`; the higher **$-prefixed**
  number is the original.
- **Per-size stock**: `label.size-enabled` (buyable) vs `label.size-disabled` (OOS). Colour swatches
  share the swatch container but have NO `size-*` class — filter on `size-` to isolate real sizes.

**Tested extractor:** `scripts/tommy_extract.py` (base64-ship to the Mac, run under the CDP venv).
Verified 2026-08-17 on two live products (`78JA876-WEB` 98% organic cotton oxford $49.75/$99.50 50% off;
`71J4179-YCI` 100% regenerative-cotton kids' tee $15.90/$26.50 40% off) — name, image, sale+original
price, %off, availability, per-size stock, colours, and composition all matched the live pages. Both
scene7 images returned `200 image/jpeg` from the VPS (no hotlink block). Output per URL:
`{url, style, name, image, currency, price, original_price, pct_off, availability, composition,
natural_pct, sizes:[{size,in_stock}], colors:[], any_size_in_stock}`.

```js
// runs in the CDP page context after ~14s render
(() => {
  const lds=[...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s=>{try{return JSON.parse(s.textContent);}catch(e){return null;}}).filter(Boolean);
  const p=lds.find(j=>j['@type']==='Product'); const o=(p&&(Array.isArray(p.offers)?p.offers[0]:p.offers))||{};
  const fibre=/cotton|polyester|elastane|wool|linen|viscose|nylon|silk|cashmere|lyocell|spandex|acrylic|rayon|modal|hemp/i;
  const comp=[...document.querySelectorAll('div.content-column, *')]
    .filter(e=>e.children.length===0 && /\d{1,3}\s*%/.test(e.textContent) && fibre.test(e.textContent))
    .map(e=>e.textContent.trim())[0];
  const sizes=[...document.querySelectorAll('label[class*=size-]')]
    .map(l=>({size:(l.getAttribute('aria-label')||l.textContent).trim(), in_stock:/size-enabled/.test(l.className)}));
  return {name:p&&p.name, image:p&&(Array.isArray(p.image)?p.image[0]:p.image), price:o.price,
          avail:String(o.availability||'').replace(/https?:\/\/schema\.org\//,''), comp, sizes};
})()
```

**Product URL shape:** `https://ca.tommy.com/en/<dept>/.../<slug>/<STYLE>-<COLOR>.html`.
Find candidates via `web_search "site:ca.tommy.com <category> <keyword>"` — snippets often carry the
`FABRICATION`/composition line and the price directly.

**Failure modes**
- Akamai HARD-403s the VPS on *every* transport (curl, web_extract, OCAPI, `.json`). Unlike Children's
  Place (Akamai but retry clears), retrying web_extract does NOT help — go straight to Mac CDP.
- **`%off` pollutes a naïve price scrape.** `[...].match(/\$?(\d+...)/)` over `"$26.50 CAD $15.90 CAD 40% off"`
  reads `40` as the max → wrong original price. Fix: only match **`$`-prefixed** amounts
  (`/\$\s?(\d+(?:\.\d\d)?)/`); parse `%off` separately. (This bit the first extractor run and is the one
  non-obvious trap.)
- JSON-LD is a single `Product`, so it carries product-level stock only — for per-size stock you MUST
  read `label.size-enabled/-disabled` from the DOM. Colours are in the same swatch group; filter on the
  `size-` class prefix so a colour name isn't mistaken for a size.
- Many kids' basics are "regenerative"/"organic" cotton (100% natural). Adult oxfords are frequently
  98% cotton / 2% elastane — clears a 70% natural gate. But "TH Performance"/"wicking"/quick-dry lines
  are predominantly synthetic — read `composition`, don't trust "cotton" in the title.

## Roots (CA) — JSON-LD `Product` + static PDP-HTML composition & stock. NO bot wall, VPS-side.

Canada, mid/upper-mid — **very natural-fibre-friendly**: heavy heritage cotton fleece
(the Original/Cooper sweats lines), plus tees, sweatshirts, and kids' basics. Deep 80–100%
organic-cotton catalogue; kids 2T–14 and adults share one platform. Confirmed in Sumeet's
household fit (not YNAB-confirmed but a natural-fibre workhorse). Domain **`roots.com`**;
locale path `/ca/en/` (US is `/us/en/`). Runs on **Salesforce Commerce Cloud (Demandware)**.
Verified 2026-08-17.

**Which rung worked: JSON-LD + static HTML (rung 1/3) — ALL VPS-side, plain `curl`/`urllib`.**
Unlike the other Demandware CA sites in this file (Carter's = PerimeterX, Tommy = Akamai — both
hard-403 the VPS and force Mac CDP), **Roots has NO bot wall**: `curl -A <desktop UA>` on a PDP
returns `HTTP 200` with the full server-rendered HTML. No exit node, no Mac delegation, no
`web_extract` needed. (The root `/` 302-redirects `→ /ca/en/homepage`; `/products.json` is 404/500
— it's Demandware, NOT Shopify, so don't try Shopify endpoints.)

**The data, once you have the PDP HTML:**
- **JSON-LD is a single `Product`** (not a `ProductGroup`): `name`, `sku`/`mpn` (= the 8-digit
  style id in the URL), `image` (array of Demandware `dw/image/v2/.../<style>_<color>_a.jpg` URLs),
  `offers.price` (current price), `offers.priceCurrency`, `offers.availability` (product-level
  `InStock`/`OutOfStock`). No per-size variant array in it.
- **Composition** is NOT in the JSON-LD. It's in the details tab under a bold label that **varies
  by department**: adults → `<strong>Fibre Content</strong><br> 80% organic cotton, 20% recycled
  polyester fleece (300gsm)`; kids → `<strong>ABOUT</strong><br />80% organic cotton, 20% recycled
  polyester fleece`. Match **either** label. NB: Roots labels blends honestly as **"recycled
  polyester"** → count as SYNTHETIC; "organic cotton" is still cotton → NATURAL. So the flagship
  Original fleece is `natural_pct` **80**, not 100 — clears a 70% rule, fails an 80%+ rule. Read
  the `%`, don't trust "cotton" in the name.
- **Per-size stock**: `<span data-attr-value="<SIZE>" class="size-value ... selectable|unselectable">`.
  `unselectable` = OOS. This reflects the DEFAULT/selected colour on the PDP.
- **Colours**: same `selectable/unselectable` on `<span class="... color-value ...">` swatches
  (`data-attr-value` = colour code like `041`/`232`; the human colour name is in nearby
  `data-attr-name="TRUE NAVY"` attrs but not always on the same tag — code is authoritative).

**Tested extractor:** `scripts/roots_extract.py` (pure `urllib`, runs on the VPS). Verified
2026-08-17 on three live products across departments — women's Original Sweatpant `54496019`
($84, 80% organic cotton / 20% recycled poly, XXS–XXL in stock, 3X/4X OOS), women's heavier
`54232174` ($84, 360gsm), and kids' `29070216` ($44, sizes 6–14 all in stock). Output per URL:
`{url, style, name, price, currency, availability, composition, natural_pct, image,
colors:[{code,name,in_stock}], sizes:[{size,in_stock}], any_size_in_stock}`.

```bash
python3 scripts/roots_extract.py \
  "https://www.roots.com/ca/en/organic-original-sweatpant-54496019.html"
# find candidates: web_search "site:roots.com /ca/en <category> <keyword>"
```

**Selectors / endpoints** (verified 2026-08-17)
| What | Where |
|---|---|
| Name / price / currency / availability / sku / image | JSON-LD `<script type="application/ld+json">` `Product` |
| Composition (fibre %) | PDP HTML: `<strong>Fibre Content</strong><br>…` (adult) or `<strong>ABOUT</strong><br />…` (kids) |
| Per-size stock | `<span data-attr-value="<SIZE>" class="size-value … selectable\|unselectable">` |
| Colour stock | `<span class="… color-value …" data-attr-value="<code>">` — same `selectable\|unselectable` |
| Product URL | `https://www.roots.com/ca/en/<slug>-<8-digit-style>.html` |

**Failure modes**
- Root `/` 302-redirects to `/ca/en/homepage`; `/products.json` → 404/500. It's **Demandware,
  not Shopify** — don't waste time on Shopify `.js`/`.json` endpoints. Go straight to the PDP HTML.
- Composition label differs adult (`Fibre Content`) vs kids (`ABOUT`) — a matcher keyed only on
  "Fibre Content" silently returns `composition: null` on kids' pages (bit the first run). Match both.
- "Recycled polyester" reads as a good thing but is SYNTHETIC for the fibre gate; the ubiquitous
  Original fleece caps at 80% natural. Don't assume Roots = 100% cotton.
- JSON-LD is a single `Product`, so per-size stock must come from the DOM `size-value` swatches,
  and those reflect only the currently-selected colour. For stock in a *specific other* colour,
  refetch the Demandware `Product-Variation` URL (the `value="…dwvar_<style>_color=<code>…"` on each
  swatch) — not needed for the common "is this piece buyable in size X" check.

## Zara (CA) — JSON-LD `ProductGroup` (per-size×colour price+stock), via CDP Chrome on the Mac

Canada, fast-fashion mid-market — kids (0–14) + adults, plus its house sub-brands that share the
platform and appear under the same JSON-LD (**Massimo Dutti** items surface with `brand:"MASSIMODUTTI"`
inside zara.com). Confirmed in Sumeet's YNAB history (bought at Square One). Natural-fibre coverage is
real but uneven — deep 100% cotton tee/shirt lines, but also heavy poly outerwear/knits, so the
composition gate matters. Domain **`www.zara.com/ca/en`**. Verified 2026-08-18.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3 (bot-wall bypass).**
From the VPS *every* path is walled and none is fixable VPS-side — it's a passive **Akamai**
fingerprint wall (identical class to Tommy Hilfiger; an exit node does NOT help, changes IP not
fingerprint):
- `curl` / `requests` on any PDP or API → `403 "Access Denied"` (`Reference #…` Akamai page).
- `web_extract` (Crawl4AI headless) → `"Blocked by anti-bot protection: Akamai block"` — a HARD
  block, retry does NOT clear it (unlike Children's Place's intermittent Akamai).
- Zara's own public JSON API (`/ca/en/products-details?productIds=…`, `/ca/en/product/<id>/extra-detail`)
  also 403s from curl, AND keys off the **internal numeric productId** (e.g. `545944283`), NOT the SEO
  id in the URL (`p01997303`) — so even from a browser it needs the internal id first. Skip it: the
  PDP's embedded JSON-LD already has everything, no second call needed.
`www.zara.com/ca/en/` loaded clean over CDP with a ~13s render wait; no interactive press-and-hold.

**The data, once the page renders (all reliable, all in ONE JSON-LD block):**
Each PDP embeds a `<script type="application/ld+json">` **`ProductGroup`** carrying:
- `name`, `brand.name` (house brand — often `ZARA`, sometimes `MASSIMODUTTI`),
- `material` (e.g. `"100% cotton"`) AND an `additionalProperty` entry
  `{propertyID:"Composition", name:"OUTER SHELL", value:"100% cotton"}` — prefer the OUTER SHELL value,
  fall back to `material`. (No accordion/XHR needed — composition is right in the JSON-LD, unlike
  Carter's/Tommy/Roots where it hides in the DOM.)
- `image[]` — clean `static.zara.net/...jpg?w=1920` CDN URLs (return `200 image/jpeg` from the VPS, no
  hotlink block — the CDN is NOT behind the shop's Akamai wall).
- **`hasVariant[]` = one entry per size×colour**, each `{size, color, sku, offers:{price, priceCurrency,
  availability}}`. This gives **per-size AND per-colour price + stock directly** (`InStock`/`OutOfStock`).
  Multi-colour products list every colourway in the same block. Confirmed it discriminates correctly
  (a tee showed White/Brown/Gray InStock but Gray-S OutOfStock).

**Tested extractor:** `scripts/zara_extract.py` (base64-ship to the Mac, run under the CDP venv).
Verified 2026-08-18 on live products — `p06228935` (100% cotton tee, 3 colours, $59.90, mixed
per-size stock) and `p01634403` (100% cotton shirt, $13.18, all OOS — the classic
suspiciously-cheap-clearance case, correctly flagged `any_in_stock:false`). Output per URL:
`{url, name, brand, composition, natural_pct, material, images[], colors[],
sizes:[{size,color,price,currency,in_stock}], any_in_stock}`.

```js
// runs in the CDP page context after ~13s render — parse the ProductGroup JSON-LD
(() => {
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent);
      if (j['@type']==='ProductGroup' || j['@type']==='Product') {
        const comp = (j.additionalProperty||[]).find(a => (a.propertyID||'').toLowerCase()==='composition');
        return {name:j.name, brand:j.brand&&j.brand.name, composition:(comp&&comp.value)||j.material,
                image:(Array.isArray(j.image)?j.image[0]:j.image),
                variants:(j.hasVariant||[]).map(v => { const o=Array.isArray(v.offers)?v.offers[0]:(v.offers||{});
                  return {size:v.size, color:v.color, price:o.price,
                          avail:String(o.availability||'').split('/').pop()}; })};
      }
    } catch(e){}
  }
  return null;
})()
```

**Product URL shape:** `https://www.zara.com/ca/en/<slug>-p<8-digit-seoId>.html` (the `p0…` id is the
`productGroupID`; the internal numeric `productId` differs and isn't needed). Find candidates via
`web_search "site:zara.com/ca/en <keyword>"` — snippets carry the composition prose and the direct URL.

**Failure modes**
- Akamai HARD-403s the VPS on *every* transport (curl, web_extract, the JSON API). Retry does NOT clear
  it (unlike Children's Place). Go straight to Mac CDP; don't burn calls on the VPS.
- Zara's public JSON API keys off the **internal numeric productId**, not the URL's SEO id — and 403s
  from curl anyway. Don't bother; the JSON-LD in the PDP is complete.
- **Suspiciously low price = sold-out clearance, not a bargain** (the universal rule bites hard here):
  a $13.18 shirt came back all-OOS. Always check `any_in_stock` / per-variant `in_stock` before
  believing a price.
- Many Zara knits/outerwear/"technical" lines are predominantly polyester/acrylic/elastane → fail a
  natural-fibre gate. Read `composition`; don't trust "cotton" in a title (a "cotton blend" shirt can be
  well under threshold).
- `w=1920` on the image URL is a resize param — swap to a smaller `w=` for email thumbnails if desired;
  the base path is stable.

## la Vie en Rose (CA) — JSON-LD `ProductGroup` (per-size price+stock) + PDP `<li>` fibre bullet. NO bot wall, VPS-side.

Canada, mid-market lingerie / sleepwear / loungewear (its banner **Bikini Village** shares the
platform — swap the domain). Confirmed in Sumeet's YNAB history. Natural-fibre coverage is
genuine but split: a deep 100% cotton pyjama/PJ line and modal camis (natural under this skill's
convention), but also a lot of 100% polyester/satin sleepwear — so the composition gate matters.
Domain **`www.lavieenrose.com`**; locale path `/en/` (also `/fr/`, `/us/`). Runs on **EPiServer /
Optimizely Commerce** behind Cloudflare. Verified 2026-08-19.

**Which rung worked: JSON-LD + a small static-HTML scrape (rung 1/3) — ALL VPS-side, plain
`curl`/`urllib`.** Despite Cloudflare + a `.AspNetCore.Antiforgery` cookie, a desktop-UA `curl` on a
PDP returns **HTTP 200 with the full server-rendered HTML** — NO exit node, NO Mac CDP, NO
`web_extract` needed. (It is EPiServer, **not Shopify** and **not Demandware** — `/products.json`
404s; don't try those endpoints.)

**The data, once you have the PDP HTML:**
- **JSON-LD is a `ProductGroup`** (the 2nd `application/ld+json` block; the 1st is a
  `BreadcrumbList`). Its **`hasVariant[]` = one Product per size**, each carrying `size`, `color`,
  `material` (**primary fibre only, NO percentages**), `image[]`, and
  `offers{price, priceCurrency, availability(InStock/OutOfStock),
  priceSpecification.price = StrikethroughPrice}`. So **per-size price + stock + the original
  (strikethrough) price come straight from the JSON-LD** — no DOM class hunt.
- **Exact fibre percentages are NOT in the JSON-LD `material`** (it's just "Modal"/"Cotton"/
  "Pointelle"). The real composition is a lone bullet in the details list:
  **`<li><p>93% Modal 7% Elastane</p></li>`** (or `100% Cotton`, `100% Polyester`). Grab the one
  `<li><p>…</p></li>` whose text matches `\d+%\s*<fibre>`. NB: modal/lyocell counted **natural**
  (plant-derived regenerated cellulose) here; viscose/rayon counted synthetic per skill convention.

**Tested extractor:** `scripts/lavieenrose_extract.py` (pure `urllib`, runs on the VPS). Verified
2026-08-19 on three live products: modal cami `6010014800001` (93% Modal/7% Elastane, natural_pct
93, $13.99 strike $19.95, **all sizes OOS** — the suspiciously-cheap-clearance case, correctly
`any_in_stock:false`); cotton PJ pants `…40200878p40620` (100% Cotton, natural_pct 100, $29.95 full
price, all InStock); pointelle cami `4010086940188` (100% Polyester, natural_pct 0, $16.99 strike
$24.95, **per-size discrimination** — XL OOS, rest InStock). The image URL returned `200 image/jpeg`
from the VPS (no hotlink block). Output per URL: `{url, name, brand, category, composition,
natural_pct, primary_material, image, colors[], strikethrough_price, price_range,
sizes:[{size,color,price,currency,in_stock}], any_in_stock}`.

```bash
python3 scripts/lavieenrose_extract.py \
  "https://www.lavieenrose.com/en/gingham-floral-print-cotton-pyjama-pants-blue-ginghamflowers-40200878p40620"
# discover: web_search 'site:lavieenrose.com/en <category> <keyword>'
```

**Selectors / endpoints** (verified 2026-08-19)
| What | Where |
|---|---|
| Name / brand / category | JSON-LD `ProductGroup` (2nd `ld+json` block) |
| Per-size price / stock / original(strike) price / image | `hasVariant[].offers` + `.priceSpecification.price` + `hasVariant[].image[0]` |
| Composition (fibre %) | PDP HTML: the lone `<li><p>NN% Fibre …</p></li>` bullet |
| Product URL | `https://www.lavieenrose.com/en/<slug>-<color>-<id>` |

**Failure modes**
- **`material` in the JSON-LD is only the primary fibre, no `%`** — a gate keyed on it alone would
  read "Modal"/"Pointelle" and miss the elastane/blend. Always scrape the `<li><p>` fibre bullet
  for the real composition; that's the one non-obvious step.
- **`hasVariant[]` includes placeholder rows for OTHER colourways with NO `offers`/`image`**
  (their `size`/`color` are `null`). Skip any variant lacking `offers`, else you inject junk sizes.
- **Suspiciously low price = sold-out clearance** (universal rule bites): the $13.99 modal cami
  came back all-OOS. Always check `any_in_stock` / per-size `in_stock` before believing a price.
- The URL slug can be **stale/renamed** but still resolves by trailing id — a `/en/peach-…-4010086940188`
  URL resolved to a product now named "Hibiscus-Embroidered…". Trust the id, not the slug words.
- A lot of the sleepwear is **100% polyester/satin** → fails a natural-fibre gate. Read the
  composition; don't trust "silky"/"soft" marketing or a pretty print.

## Colour diversity — a curation rule (learned 2026-08-08)

A harvest that ignores colour converges on one colour (whatever the retailer photographs most —
usually navy/black), and the resulting cart reads as a uniform. Two-part fix:

1. **Harvest**: record the default variant's actual colour per product, plus available colourways,
   in a `colors` field. JSON-LD usually lacks colour — read it off the PDP or infer from the
   product name/slug.
2. **Curate**: before finalizing, tally colours across the whole cart. No colour should exceed
   ~30% of items; the stated palette should all be represented. Where a piece comes in multiple
   colourways, name the specific colour to buy in the item's `meta` line.

## Sport Chek (CA) — JSON-LD `Product` + `.nl-price`/`.nl-variants` DOM, via CDP Chrome on the Mac

Canada, mid-market athletic/outdoor — the "kids + adults, activewear + casual" role, and
Sumeet's fitness-angle store (confirmed in his YNAB history). Domain **`sportchek.ca`**
(`/en/pdp/...`). Runs on the **Canadian Tire / FGL "Nucleus"** stack — so sister banners
**Atmosphere, Sports Experts, Mark's, Canadian Tire, Party City** share the same DOM class
prefixes (`nl-*`) and PDP shape; the recipe should transfer with a domain swap. Natural-fibre
angle is real: house brand **Ripzone** and a lot of Nike/Under Armour/adidas/Carhartt/Vans tees
are 100% or mostly cotton (read composition — "Charged Cotton" and performance lines blend).
Verified 2026-08-19.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3 (bot-wall bypass).**
From the VPS *every* transport is walled and none is fixable VPS-side:
- `curl`/`urllib` on the PDP → `403` (Akamai edge; 471-byte body).
- `web_extract` (Crawl4AI headless) → renders only the page *chrome* (header/footer/cookie
  banner); the product body is client-side-rendered from an API it can't reach, so name/price/
  composition/sizes all come back **empty**. NOT a retry-clears-it Akamai like Children's Place —
  the shell renders "successfully" but is useless. Don't trust a 200 from web_extract here.
- The product data API (`/api/v1/product/...` on `www.sportchek.ca` AND the APIM gateway
  `apim.canadiantire.ca/v1/product/...`) → hard **Akamai `Access Denied`** from the VPS on every
  path/verb tried (v1/v2/v3, `productFamily/<id>`, `product/<id>`, `sku`, `detail`, `products`).
  The one path that got *past* Akamai, `apim…/v1/product/api/v1/product/<id>`, returned **410 Gone**
  (deprecated) — so even with the wall down that endpoint is dead. The live subscription-key
  (`ocp-apim-subscription-key` / `subscription-key` query param) leaks in the PDP's image URLs
  (`…/api/v1/product/image/<id>?…&subscription-key=<hex>`) but does NOT unlock the data API from
  the VPS. Treat the JSON API as **not reachable VPS-side** — go straight to Mac CDP.
It's a **passive fingerprint wall (Akamai)**, no interactive press-and-hold, so an exit node does
NOT help. `www.sportchek.ca` loaded clean over CDP with a ~14s render wait.

**The data, once the page renders (no API needed — read the DOM):**
- **JSON-LD `Product`** (`script[type=application/ld+json]`; there are ~6 blocks, pick
  `@type==='Product'` — the others are WPHeader/ItemList/BreadcrumbList/WPFooter/AggregateRating).
  Gives `name`, `brand.name`, `image`, and a **`description`** whose prose almost always states the
  composition ("made of 100% cotton"). No per-variant offers in the JSON-LD (unlike Carter's/Zara).
- **Composition**: best source is a dedicated leaf element `Contents: 100% Cotton.` (regex
  `^(Contents|Composition|Fabrication|Material)\s*[:\-]`). Fall back to a fibre-% run mined out of
  the JSON-LD `description` prose.
- **Price**: `.nl-price__container` leaf carries the full string — on sale it reads
  `NOW$8.88WAS±  $15.97price was $15.97Final Sale*`; at regular price just `$45.00`. Parse `NOW$…`
  first, then `WAS…$…`; a `.nl-price--total--red` element (or was>now) signals a markdown, and
  `Final Sale` in the text signals no-return clearance. `.nl-price--was` holds the strikethrough.
  (Beware: the footer's Triangle-Mastercard finance table spews `$100/$500/$1000/$1.81…` — anchor
  on the `.nl-price*` classes, never a bare `$` scan.)
- **Per-size stock**: size chips are `.nl-variants__variant` divs (colour swatches are the same
  class + `--colour-swatches`; filter those out, and drop the `Regular`/`Tall` length chips). An
  out-of-stock size carries a `--disabled/--unavailable/--soldout/--out-of-stock` class modifier or
  `aria-disabled=true`. NOTE: on a fully in-stock product all chips read in-stock (verified on the
  Nike polo: S–XXL all OK); a single-colour clearance item (Ripzone tee) rendered **no** size chips
  at all → `sizes: []` (verify on the live page before promising a size).

**Tested extractor:** `scripts/sportchek_extract.py` (base64-ship to the Mac, run under the CDP
venv). Verified 2026-08-19 on two live products:
- `82641425` Nike Men's Core Cotton Polo → 100% cotton, natural_pct 100, $45.00 (no sale),
  S/M/L/XL/XXL all in stock, image 200 image/jpeg.
- `83828003` Ripzone Men's Giles Photo Tee → 100% cotton, natural_pct 100, **$8.88 was $15.97
  Final Sale**, no size chips rendered, image 200 image/jpeg.
Output per URL: `{url, name, brand, image, price, was_price, on_sale, final_sale, currency,
composition, natural_pct, sizes:[{size,in_stock}], description, item_id}`.

**Selectors / shapes** (verified 2026-08-19)
| What | Where |
|---|---|
| Name / brand / image / desc | JSON-LD `@type==='Product'` (`name`, `brand.name`, `image`, `description`) |
| Composition | leaf `Contents:/Composition:/Fabrication:` element; fallback = fibre-% run in `description` |
| Price (now / was / sale) | `.nl-price__container` full text; `.nl-price--total(--red)`, `.nl-price--was` |
| Per-size stock | `.nl-variants__variant` (not `--colour-swatches`); OOS = `--disabled/--unavailable/--soldout` |
| Image (fallback) | `meta[property=og:image]` |
| Product URL | `https://www.sportchek.ca/en/pdp/<slug>-<9digit>f.html` (the 9-digit before `f` is the item id) |
| Leaked API key | image URLs carry `subscription-key=<hex>` — does NOT unlock the data API from the VPS |

**Failure modes**
- Akamai passive wall from the VPS on curl + the data API (www AND apim gateway). web_extract
  returns a *hollow* 200 (chrome only). All fixed by Mac CDP; exit node won't help (fingerprint, not IP).
- The live `/v1/product/api/v1/product/<id>` APIM path is **410 Gone** even past the wall — don't
  chase the JSON API; the DOM has everything.
- Colour swatches share the `.nl-variants__variant` class — filter `--colour-swatches` or you'll
  read blank chips as sizes.
- Finance/rewards boilerplate in the footer is full of `$` amounts; never regex a bare `$` for price.
- Clearance/single-colour items may render **zero** size chips (`sizes: []`) — treat as "verify size
  on the live page", not "one size". A very low "Final Sale" price is real clearance, likely thin stock.

## Walmart.ca (George etc.) — JSON-LD + `__NEXT_DATA__` specs, via CDP Chrome on the Mac with a HOMEPAGE WARM-UP

Canada, cheapest general-merch + kids/adult apparel workhorse — the "kids, play clothes" role, and
its house brand **George** is heavily 100% cotton (tees, polos, PJs, basics) so it's a solid
natural-fibre source at rock-bottom prices ($8 for a 2-pack tee). Confirmed in Sumeet's YNAB.
Domain is **`walmart.ca/en`**; runs on a Next.js frontend (`__NEXT_DATA__`) behind PerimeterX.
Verified 2026-08-19.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3 (bot-wall bypass), with a twist.**
From the VPS *every* path is walled: `curl` → 307 `blocked - redirecting` → `/blocked?...`
px-captcha page; `web_extract` (Crawl4AI headless) → `"Blocked by anti-bot protection: PerimeterX
block"`. It's a passive fingerprint + interactive "Verify Your Identity" wall, so an exit node does
NOT help.
- **The non-obvious twist: even a real windowed Chrome on the Mac gets bounced to `/blocked`
  ("Verify Your Identity") on a COLD direct hit to a `/ip/...` product URL.** The fix is to
  **warm the session on the homepage first** (`https://www.walmart.ca/en`, ~12s), THEN navigate to
  each product **in the SAME tab** via `location.assign(url)`. The warmed session carries the
  PerimeterX cookie and the product page then renders clean. A fresh tab per product re-triggers the
  wall. This single trick is what makes Walmart tractable — without it you loop on `/blocked`.
- NO interactive press-and-hold once warmed; the homepage itself loads clean.

**The data, once the page renders:**
- **JSON-LD**: a single-size product emits `@type: "Product"` (`name`, `brand.name`, `sku`, `image`,
  `offers.price`/`priceCurrency`/`availability`). A multi-size product emits `@type: "ProductGroup"`
  with `hasVariant[]` — one entry **per size** with `size` + `offers.price`/`availability`
  (`InStock`/`OutOfStock`). NOTE: `hasVariant` also contains **empty entries for other colourways**
  (no `size`/`offer`) — filter to entries that have a `size` or `price`.
- **`__NEXT_DATA__`** (`#__NEXT_DATA__` script) carries a structured **`specifications`** array
  under `props.pageProps` — `[{name:"Clothing Size",value:"4"}, {name:"Brand",value:"George"}, …]`.
  Flatten to a dict; it gives size/colour/brand/UPC/Walmart-item#. A **`Fabric Material`/
  `Composition`** spec is the authoritative composition WHEN PRESENT.
- **Composition is often NOT a spec on cheap George items** — it lives in prose in the
  `longDescription` ("Made of 100% cotton, …"). Extract fibre-`%` pairs from the description (and
  body text as fallback); dedup case-insensitively (`100% cotton` vs `100% Cotton`) or natural_pct
  double-counts. Cap natural_pct at 100.
- **Image**: JSON-LD `image` or `og:image` — a `https://i5.walmartimages.ca/asr/<uuid>.<hash>.jpeg`
  URL; returns `image/jpeg`, no hotlink block.

**Tested extractor:** `scripts/walmart_extract.py` (base64-ship to the Mac, run under the CDP venv;
it does the homepage warm-up + same-tab navigation itself). Verified 2026-08-19 on three live George
products (`6000208542550` boys' tee 2-pack InStock, `6000196741979` kids' tee 2-pack OutOfStock,
`6000208538686` toddler tee 2-pack InStock) — name, $8 CAD price, `100% cotton` (natural_pct 100),
per-size stock, and image (200 image/jpeg) all matched the live pages. Output per URL:
`{url, name, brand, sku, price, currency, availability, image, composition, natural_pct,
sizes:[{size,price,availability}], specs:{…}, desc}`.

**Selectors / shapes** (verified 2026-08-19)
| What | Where |
|---|---|
| Name / brand / sku / image | JSON-LD `Product`/`ProductGroup` (`name`, `brand.name`, `sku`, `image`) |
| Price / currency / availability | JSON-LD `offers` (single) or `hasVariant[].offers` (per size) |
| Per-size stock | `hasVariant[].size` + `offers.availability` (`InStock`/`OutOfStock`); drop empty colour entries |
| Specs (size/colour/brand/UPC/item#) | `__NEXT_DATA__` `props.pageProps` → `"specifications":[{name,value}]` |
| Composition | `Fabric Material`/`Composition` spec if present; else fibre-% pairs in `longDescription` |
| Image | JSON-LD `image` or `meta[property=og:image]` → `i5.walmartimages.ca/asr/...jpeg` |
| Product URL | `https://www.walmart.ca/en/ip/<slug>/<10-digit-id>` |

**Failure modes**
- **Cold direct hit to a product URL → `/blocked` "Verify Your Identity"**, even on a real Mac
  windowed Chrome over CDP. MUST warm on the homepage first, then same-tab `location.assign`. A per-
  product fresh tab re-triggers the wall. This is THE trap here.
- PerimeterX walls the VPS on every transport (curl `/blocked` px-captcha; web_extract "PerimeterX
  block"). Retrying does NOT clear it (unlike Akamai on Children's Place). Go to Mac CDP.
- Composition is usually prose, not a spec, on George basics — regex fibre-% pairs and dedup
  case-insensitively, else natural_pct inflates (seen: 200 before the fix).
- `hasVariant[]` mixes real size variants with empty other-colour stubs — filter on `size`/`price`.
- Marketplace 3rd-party sellers (non-George, e.g. "Sales Today Clearance!" listings) may lack clean
  JSON-LD/specs and quote junk composition — prefer first-party George / Walmart-brand items.

## Frank And Oak (CA) — Shopify `/products/<handle>.js` (everything incl. composition). NO bot wall.

Canada, mid-market men's/women's with a strong sustainability + natural-fibre angle — deep
**100% cotton / linen / hemp / TENCEL-lyocell / pima** lines (a browse of 30 SKUs was almost
entirely natural fibres; the only synthetic seen was 2% spandex in stretch shorts/pants). A great
adult natural-fibre source. It's a Shopify store on **`www.frankandoak.com`**, and — unlike the
Cloudflare storefront root — the Shopify product JSON endpoints are **wide open from the VPS**:
plain `curl`/`urllib`, no exit node, no Mac delegation. Verified 2026-08-20.

**Which rung worked: Shopify JSON (rung 2) — all VPS-side, one request per product.**
`/products/<handle>.js` is the whole money block:
- `price` / `compare_at_price` in **CENTS**; top-level `available`.
- `variants[]` each with `option1` = size and a real **`available`** boolean → **per-size stock
  directly** (no `--unavailable` class hunt, no accordion click).
- `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`).
- **Composition is IN the `.js`** — `description` (== `body_html`) carries a
  **`Content: <fibres>`** line, e.g. `Content: 100% Cotton`, `Content: 55% Hemp, 45% Organic Cotton`,
  `Content: 55% Linen, 45%Cotton` (note: sometimes no space after the comma). No separate PDP-HTML
  fetch needed (unlike Reitmans). Parse the fibre-% pairs and sum naturals for the gate.

```bash
# price/stock/image/variants/composition — one call, VPS-side:
curl -s -A "$UA" "https://www.frankandoak.com/products/<handle>.js"
#   .price (cents), .compare_at_price, .available, .variants[].{option1,available,price},
#   .featured_image, .description -> "…Content: 100% Cotton…"
```

**Tested extractor:** `scripts/frankandoak_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-20 on three live products:
- `mens-knit-t-shirt-moss-green-2mkt0031fe-moss` → "100% Cotton", natural_pct 100, $39.00, all 6 sizes in stock.
- `mens-woven-pants-pebble-khaki-2mwp005fe-ekha` → "55% Linen, 45%Cotton", natural_pct 100, $129.00.
- `mens-knit-t-shirt-white-2mkt010fe-wht` → "70% Cotton, 30% Hemp", natural_pct 100, $45.00.
Output per URL: `{url, handle, title, vendor, price, compare_at_price, on_sale, available,
composition, natural_pct, image, sizes:[{size,price,available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-20)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in cents; `variants[].available`) |
| Composition (fibre %) | `.js` `description`, the `Content: <fibres>` line |
| Image | `.js` `featured_image` (`//cdn.shopify.com/...` → prefix `https:`) — returns `image/jpeg` |
| Product URL | `https://www.frankandoak.com/products/<handle>` |
| Discovery / catalog | `/products.json?limit=250` (handle, title, tags, body_html) |

**Failure modes**
- **`/search/suggest.json` is DISABLED** (returns empty), as is `/collections/all/products.json`
  filtered oddly — but the top-level **`/products.json?limit=250`** works and lists everything.
  For discovery use that or `web_search "site:frankandoak.com <keyword>"`.
- The storefront HTML root is behind Cloudflare (`server: cloudflare`, redirects/complexity headers),
  but the **`.js`/`.json` product endpoints are NOT walled** — don't be scared off by the CF root;
  go straight to the JSON.
- `vendor` reads `ThreadC` (a manufacturing/house label), not "Frank And Oak" — label the brand
  manually. `brand` is not reliably meaningful.
- Composition comma spacing is inconsistent (`45%Cotton` vs `45% Cotton`) — parse with a tolerant
  `(\d+)\s*%\s*([A-Za-z™ -]+)` regex, not a fixed split.
- Count TENCEL™/lyocell as **natural** (plant-derived); the lone synthetic seen is `2% Spandex` in
  stretch bottoms (→ natural_pct 98, clears any sane threshold). No viscose/rayon seen in the sample.

## Indigo / Chapters (indigo.ca) — Shopify `.js` + JSON-LD `ProductGroup`. NO bot wall, VPS-side.

Canada — the **books & gifts** store (the "gift track" bookstore role: canonical books
on a person's craft, plus home/decor/candles/stationery gifts). Confirmed in Sumeet's
YNAB history. **The old `chapters.indigo.ca` domain is retired** — it 301-redirects to
`www.indigo.ca` (and legacy `.../<isbn>-item.html` PDPs bounce to `/search?q=<isbn>`).
The new site is a **Shopify store** with **NO bot wall from the VPS** — plain `urllib`/
`curl` work, no exit node, no Mac delegation. Verified 2026-08-20.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML JSON-LD read — all VPS-side.**

- **`/products/<handle>.js`** is the money endpoint (one request, buyable facts):
  `price`/`price_min`/`compare_at_price` in **CENTS**, top-level `available`, `type`
  (`Book` | `GM` for gifts/merch), `vendor`, `tags` (`BOOK`, `YCRF_BOOK`, `notify-when-available`),
  `featured_image` (protocol-relative `//cdn.shopify.com/...` -> prefix `https:`), and
  **`variants[]` = one per FORMAT for books** (Hardcover / Paperback / Audiobook / Kobo eBook),
  each with `price` (cents) + `available` boolean -> **per-format price & stock directly**.
  WARNING: top-level `price`/`price_min` is the **lowest across formats** — usually the eBook.
  For a physical gift, read the Hardcover/Paperback entry in `variants[]`, not the top-level price.
- **PDP HTML `/products/<handle>`** carries two `application/ld+json` blocks; block[1] is a
  **`ProductGroup`** whose `hasVariant[]` gives per-variant `sku`/`gtin13` (= **ISBN13** for books),
  `brand.name` (= **publisher**), `offers.price` (DOLLARS), `offers.availability`, plus a top-level
  `aggregateRating` (`ratingValue`, `ratingCount`). The **author is NOT in JSON-LD** — it's in the
  `<title>`: `"<Book Name> by <Author>, (<Format>) | Indigo"` (regex `\bby\s+(.+?),\s*\(`).
- **Discovery**: `/search/suggest.json?q=<terms>` with `resources[type]=product` &
  `resources[limit]=N` (URL-encode the brackets: `resources%5Btype%5D=product`) ->
  `resources.results.products[]` with `title, handle, url, price` (**DOLLARS** here, unlike `.js`),
  `available`, `type`, `vendor`, `featured_image`. Works for books and gift/home items.
  `web_search "site:indigo.ca <keyword>"` also returns clean `/products/<handle>` deep-links.

**Tested extractor:** `scripts/indigo_extract.py` (pure `urllib`, runs on the VPS; `--full`
adds ISBN/publisher/author/rating from the PDP). Verified 2026-08-20 on three live products:
- `atomic-habits` -> Hardcover $27.00 InStock, Audiobook $19.99 **OOS**, Kobo eBook $16.99 InStock;
  ISBN 9780735211292, publisher "Penguin Publishing Group", author "James Clear", rating 4.8 (567).
- `the-atomic-habits-workbook` -> Paperback $36.00, Kobo $16.99, both InStock; ISBN 9798217180509.
- `floral-decal-candle-11oz` (a GM gift) -> $10.00 (compare-at $28.00, on sale), 2 scent variants
  both InStock, vendor "Foundry Candle Co.". Output per URL: `{handle,url,title,type,vendor,price,
  compare_at_price,on_sale,available,image,formats:[{format,price,available}],isbn,publisher,author,
  rating,rating_count}`.

**Selectors / endpoints** (verified 2026-08-20)
| What | Where |
|---|---|
| Per-format price + stock | `/products/<handle>.js` -> `variants[]` (`title`=format, `price` cents, `available`) |
| Overall price / sale | `.js` `price`/`compare_at_price` (CENTS; `price` = lowest format, often eBook) |
| Type (book vs gift) | `.js` `type`: `Book` \| `GM` |
| Publisher / brand | ProductGroup JSON-LD `hasVariant[0].brand.name` (`.js` `vendor` is often `"None"` for books) |
| ISBN13 | ProductGroup JSON-LD `hasVariant[].gtin13` (= `sku`) |
| Author | PDP `<title>`: `… by <Author>, (<Format>) \| Indigo` |
| Rating | ProductGroup JSON-LD `aggregateRating.ratingValue` / `.ratingCount` |
| Image | `.js` `featured_image` (`//cdn.shopify.com/...` -> prefix `https:`) |
| Discovery | `/search/suggest.json?q=…` + `resources%5Btype%5D=product` (prices DOLLARS) |

**Failure modes**
- `chapters.indigo.ca` is DEAD (301 -> `indigo.ca`); legacy `-item.html` ISBN PDPs -> `/search?q=<isbn>`.
  Always use the new `/products/<handle>` shape; get handles from `web_search site:indigo.ca` or `suggest.json`.
- `.js` `vendor` is frequently `"None"` for books — for publisher, read the ProductGroup `brand.name`
  (needs the `--full`/PDP fetch), not `vendor`.
- **Price unit differs by source**: `.js`/`variants[].price` are **cents**; `suggest.json` prices are **dollars**.
- Top-level `.js` `price` = the cheapest format (usually Kobo eBook). Don't quote it as "the book's price"
  for a physical gift — pick the Hardcover/Paperback variant.
- A `notify-when-available` tag / a format with `available:false` = that format is OOS even though the
  product page loads (e.g. Atomic Habits audiobook was OOS while hardcover + eBook were in stock).
- Fibre composition is N/A (books/gifts) — the natural-fibre gate doesn't apply here; this is a gift-track store.

## ALDO (CA) — JSON-LD `ProductGroup` + Materials accordion, from the rendered PDP HTML. NO bot wall.

Canada, mid-market footwear + accessories (bags, jewelry, sunglasses). Confirmed in Sumeet's YNAB
history. **Adult footwear only** — the skill's hard rule is NEVER order kids' shoes (fit needs
in-person measuring); ALDO is adult sizing, so it's fine for the adult track. Domain
**`aldoshoes.com`** → redirects to **`aldoshoes.com/en-ca`**. It's a Shopify store, but see the
footwear-`.js`-404 trap below. **No bot wall from the VPS** — plain `urllib`/`curl` render the full
PDP; no exit node, no Mac delegation. Verified 2026-08-21.

**Which rung worked: JSON-LD from the rendered PDP HTML (rung 3) — all VPS-side.**
Footwear composition is leather/suede/textile/synthetic, NOT fibre-%: judge natural (leather,
suede, nubuck, canvas, cotton, wool) vs synthetic from the `Material:`/`Lining:`/`Sole:` labels.

- **JSON-LD `ProductGroup`** on the PDP is the money block: `hasVariant[]` = one entry **per size**,
  each `{name:"<Product> - <size>", sku, image, offers.price, offers.priceCurrency,
  offers.availability}` → **per-size price + stock directly** (`InStock`/`OutOfStock`). The
  top-level `size`/`image`/`material` fields are `null` — read size from each variant's `name`
  (split on `" - "`), image from the variant's `image`.
- **Composition** is NOT in the JSON-LD. It's in the **"Materials" accordion in the static HTML**
  (no click/expand needed — curl gets it): `Material: Smooth Leather  Lining: Synthetic  Sole: Rubber`.
  Grab the block between `Materials` and the next `</ul>`, strip tags, regex out `Material:`,
  `Lining:`, `Sole:`.

```bash
# Full rendered PDP (static; en-ca prefix REQUIRED — see failure modes):
curl -s -L -A "$UA" "https://www.aldoshoes.com/en-ca/products/fez-black" -o pdp.html
# JSON-LD ProductGroup (per-size price+stock+image) + Materials accordion → composition
python3 scripts/aldo_extract.py fez-black levie-black    # bare handle or full URL both work
```

**Tested extractor:** `scripts/aldo_extract.py` (pure `urllib`, runs on the VPS). Verified
2026-08-21 on two live products:
- `fez-black` → "Smooth Leather" (lining Synthetic, sole Rubber), $170.00 CAD, sizes 7/7.5 OOS,
  8–12 InStock, 13/14 OOS.
- `levie-black` → "Smooth Leather" (sole Rubber), $225.00 CAD, size 5 OOS, 6–9 InStock, 10–12 OOS.
Output per URL: `{url, name, brand, image, currency, price_min, price_max, material, lining, sole,
materials_raw, natural_material, sizes:[{size, sku, price, availability}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-21)
| What | Where |
|---|---|
| Per-size price / stock / sku / image | PDP JSON-LD `ProductGroup.hasVariant[]` (`offers.price`, `offers.availability`, `name` holds the size after `" - "`) |
| Composition | static PDP HTML, `Materials` accordion → `Material:` / `Lining:` / `Sole:` labels |
| Product image | each variant's `image` (or `og:image` for the default colourway) |
| Product URL | `https://www.aldoshoes.com/en-ca/products/<handle>` |
| Handle | tail after `/products/`, e.g. `fez-black`, `levie-black`, `<name>-<colour>-<styleid>` |
| Discovery | `products.json?limit=250` lists handles/types/`variants[].available`; or `web_search "site:aldoshoes.com <keyword>"` |

**Failure modes**
- **Footwear `.js`/`.json` 404 despite being Shopify.** `https://www.aldoshoes.com/products/<handle>.js`
  works for SOME accessory/jewelry handles but **404s for footwear** — do NOT rely on the standard
  Shopify `.js` money endpoint here. Use the rendered PDP JSON-LD instead (it's static, un-walled).
- **The `en-ca` prefix is required for the PDP.** `/products/<handle>` (no locale) → **404**;
  `/en-ca/products/<handle>` → 200. The extractor auto-prepends it when given a bare handle.
- `products.json` at the root DOES work (VPS-side) and is good for enumerating handles + top-level
  `available`, but it lacks per-size stock and composition — use it only for discovery.
- `search/suggest.json` returns an **empty** `products` array (predictive search is disabled/gated);
  don't use it for discovery — use `products.json` or `web_search` instead.
- `material` in the JSON-LD is `null`; composition only exists in the Materials accordion HTML.
- Footwear is leather/suede/synthetic, not fibre-%: `natural_material` is a leather/suede/canvas
  heuristic on the `Material:` label, not a fibre percentage. A `Lining: Synthetic` is normal for
  leather shoes and doesn't fail a natural gate (the upper is what matters for the material rule).

## The Ordinary / Deciem (CA) — JSON-LD `Product` + static INCI attribute. No bot wall, VPS-side.

Canada, affordable skincare (a **gift / personal-care** direction, not apparel). `theordinary.com`
and parent `deciem.com` run on Salesforce Commerce Cloud (Demandware). Confirmed in Sumeet's YNAB
history (beauty). Sister brands **NIOD** and **The Chemistry Brand** share the platform — swap the
domain and the recipe transfers. **No bot wall from the VPS** — plain `urllib`/`curl` return the
full rendered HTML (200); no Cloudflare, no exit node, no Mac delegation. Verified 2026-08-21.

**Which rung worked: JSON-LD (rung 3) + one static-HTML attribute — all VPS-side, rung 1 transport.**
- Demandware `products.json` / `/products/<handle>.json` do **not** exist here (the site is not a
  Shopify store — those paths return the Demandware HTML shell, not JSON). Don't chase them.
- The **PDP JSON-LD `Product`** block carries the money fields: `name`, `sku`, `brand`, `image`,
  `offers.price` (CAD), `offers.priceCurrency`, `offers.availability` (`InStock`/`OutOfStock`).
- **INCI ingredient list** (the "composition" analog for skincare — there's no fibre %) is in the
  *static* HTML as a single attribute:
  **`<p class="ingredients-flyout-content" data-original-ingredients="Aqua (Water), Niacinamide, …">`**.
  Present in the raw HTML — no click/accordion-expand or XHR needed. Surface it so a clean/natural-
  ingredient preference can be applied (parse the comma list; e.g. flag "Phenoxyethanol", fragrance,
  drying alcohols as the user's rules dictate).
- **Size** is encoded in the `sku` slug tail (e.g. `rdn-niacinamide-10pct-zinc-1pct-30ml` → `30ml`).
  Some skus are bare GTINs (`769915233490`) with no size — read the `30ml`/`60ml`/`100ml` tile text
  from the HTML instead. The catalog is single-size per PDP, so there's no per-size stock grid.

```bash
# name / price(CAD) / availability / image + full INCI — all VPS-side:
python3 scripts/theordinary_extract.py \
  "https://theordinary.com/en-ca/niacinamide-10-zinc-1-serum-100436.html"
# -> {name, sku, brand, price, currency, availability, in_stock, size, image, ingredients, description}
```

**Tested extractor:** `scripts/theordinary_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-21 on two live products:
- `niacinamide-10-zinc-1-serum-100436` → $6.60 CAD InStock, 30ml, INCI `Aqua (Water), Niacinamide,…`.
- `hyaluronic-acid-2-b5-serum-with-ceramides-100637` → $12.00 CAD InStock, INCI `Aqua (Water),
  Sodium Hyaluronate,…`.

**Selectors / endpoints** (verified 2026-08-21)
| What | Where |
|---|---|
| Name / sku / brand / image | PDP JSON-LD `Product` (`script[type=application/ld+json]`, the `@type:"Product"` one) |
| Price (CAD) / availability | JSON-LD `offers.price` / `offers.availability` (`InStock`/`OutOfStock`) |
| Ingredients (INCI) | static HTML `<p class="ingredients-flyout-content" data-original-ingredients="…">` |
| Size | `sku` slug tail `-<NN>ml`, else `\d+\s?ml` in the tile text |
| Product URL | `https://theordinary.com/en-ca/<slug>-<productId>.html` |
| Discovery | `web_search "site:theordinary.com/en-ca <keyword>"` (snippets carry the PDP URL) |

**Failure modes**
- **NOT a Shopify store** — `/products/<handle>.json` and root `products.json` return the Demandware
  HTML shell, not JSON. Use the PDP JSON-LD, not Shopify endpoints.
- There are **two JSON-LD blocks** on a PDP — a `Product` and an `FAQPage`. Filter on
  `@type == "Product"` (the FAQ one has `offers: null`).
- `offers.url` is an **empty object `{}`**, not the product URL — use the PDP URL you fetched.
- `gtin`/`additionalProperty` are near-useless (`FSA Eligible: false`); don't rely on them.
- Skincare has **no fibre-% composition** — the natural-fibre gate doesn't apply. The relevant filter
  is the INCI list (fragrance/preservatives/actives), which the skill's material rule doesn't cover
  directly; treat it as informational unless the user states an ingredient preference.

## Crocs (CA) — masterData JS block (per-size ATS stock) + PDP JSON-LD. NO bot wall, VPS-side.

Canada, mid-market footwear (adults + kids). Confirmed in Sumeet's YNAB history. Domain
**`crocs.ca`** (`,en_CA,pd.html` suffix); Salesforce Commerce Cloud (Demandware). US `crocs.com`
is the same platform → recipe transfers (swap the locale suffix). **No bot wall from the VPS** —
plain `urllib`/`curl` with a browser UA returns HTTP 200; no exit node or Mac delegation. Verified
2026-08-22.

**Which rung worked: raw PDP HTML via `urllib` (rung 1-ish) — TWO server-rendered sources:**
1. **JSON-LD `Product`** block → `name`, `brand`, `image` (Cloudinary), headline `offers.price` +
   `priceCurrency`, and `aggregateRating` (`ratingValue`/`ratingCount`). Clean.
2. **`app.product.data.cache["<styleid>"].masterData = {...}`** — a JS assignment carrying the
   *money* block (regex `\.masterData\s*=\s*(\{"variations":.*?\});?\s*</script>`, parses as plain
   JSON):
   - **`variations`**: one entry **per colour×size SKU** → `{color, size, inStock (bool),
     ATS (int qty), UPC}`. Aggregate across colours for per-size availability + total ATS.
   - **`colors`**: a dict **keyed by price string** (so it models a sale) → `{isSale, price,
     regularPrice, regularFormatted, colors[], oosColors[]}`. First value = the live price tier;
     `isSale`/`regularPrice` give sale detection, `oosColors[]` = sold-out colourways.
   - **`skusBySize.oosSkus`**, **`tagMinPrice`**, **`isOOS`** for quick top-level checks.

```python
import re, json, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
html = urllib.request.urlopen(urllib.request.Request(
    "https://www.crocs.ca/classic-clog/10001,en_CA,pd.html",
    headers={"User-Agent": UA, "Accept": "text/html"}), timeout=30).read().decode("utf-8","replace")
md = json.loads(re.search(r'\.masterData\s*=\s*(\{"variations":.*?\});?\s*</script>', html, re.S).group(1))
# md["variations"]["10001-001-M5W7"] -> {"size":"M5W7","inStock":true,"ATS":804,...}
```

**Tested extractor:** `scripts/crocs_extract.py` (pure `urllib`, runs on the VPS). Verified
2026-08-22 on two live products:
- `10001` (Classic Clog) → $64.99 CAD, 21 colours (3 OOS), 16 unisex sizes all in stock,
  rating 4.5 (30229).
- `206991` (Kids' Classic Clog) → $49.99 CAD, 16 colours (8 OOS), 9 kids' sizes (C11–J6) in stock,
  rating 4.5 (1690).
Output per URL: `{url, style_id, name, brand, image, price, currency, on_sale, regular_price,
rating, rating_count, num_colors, oos_colors[], sizes:[{size,in_stock,ats}], any_in_stock, details[]}`.

**Selectors / endpoints** (verified 2026-08-22)
| What | Where |
|---|---|
| Name / brand / image / rating / headline price | JSON-LD `Product` block (`@type == "Product"`) |
| Per-size stock + ATS qty | `masterData.variations` (regex-extract the JS assignment, parse as JSON) |
| Sale + OOS colours | `masterData.colors` (dict keyed by price string; first value = live tier) |
| Product URL | `https://www.crocs.ca/<slug>/<styleid>,en_CA,pd.html` |
| Style id | tail segment before `,en_CA,pd.html` (e.g. `10001`, `206991`) |
| Image | JSON-LD `image` — Cloudinary `https://media.crocs.com/images/.../products/<style>_<color>_ALT100/...` |
| Discovery | `web_search "site:crocs.ca <keyword>"` (snippets carry the `,en_CA,pd.html` PDP URL) |

**Failure modes**
- **web_extract (Crawl4AI) strips `<script>`, so it loses BOTH JSON-LD and `masterData`** — you get
  visible price/title/colours/sizes but NO per-size stock and NO structured price. Use raw
  `urllib`/`curl` (Crawl4AI is fine as a sanity-check of the visible price only).
- **Sizes are unisex `M#W#` for adults** (e.g. `M5W7` = men's 5 / women's 7) and `C#`/`J#` for kids
  (`C11` little-kid, `J1`+ big-kid/"junior"). Map the recipient's foot length to the Crocs size
  chart — and per the skill's rule, **never order kids' shoes**; emit a measure-first + cm→size
  table instead. Adults pick their own size.
- **Croslite = EVA-type foam, NOT a woven fabric** → the natural-fibre gate does NOT apply to Crocs
  footwear. The only material note is the `Details` bullet "made with N% bio-circular material"
  (surfaced as `details[]`); there is no fibre-% composition to compute.
- The `Details` bullet list is **rendered twice** on the PDP (main + accordion) — dedup or you get
  doubled bullets. The extractor already dedups.
- `masterData.colors` is keyed by a **price string** not a colour code; if a product ever had two
  price tiers (some on sale) there'd be >1 key — the extractor takes the first (live) tier, which is
  correct for the common single-tier case but re-check for a mixed-sale product.

## The Body Shop (CA) — Shopify `.js` (price/stock) + PDP-HTML INCI span. No bot wall.

Canada, mass beauty/personal-care (body butter, shower gel, skincare, gift sets) — a **gift /
personal-care** store, confirmed in Sumeet's YNAB history. Cruelty-free / "ingredients of natural
origin" is its whole positioning. Domain **`thebodyshop.ca`**; it's a **Shopify** store
(`myshopify_domain njstuz-x2.myshopify.com`), CAD. **No bot wall from the VPS** — plain
`urllib`/`curl` work; no exit node, no Mac delegation. Verified 2026-08-23.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.**
(web_extract also renders the PDP clean as a fallback, but the `.js` API is cleaner.)
- **`/products/<handle>.js`** is the money endpoint: `title`, `price`/`compare_at_price`
  (in **CENTS**; `compare_at_price` set only when on sale), top-level `available`, `type`,
  `vendor`, `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`), and a
  `variants[]` grid each with `title` (the **size**, e.g. `200ML`/`400ML`), `sku`, `price`, and a
  real **`available`** boolean → **per-size price + stock directly**. (`.js` gives `available`;
  `.json` does NOT — use `.js`.)
- **Cosmetics, not fabric** → the personal-shopper natural-**fibre** gate is **N/A**. The analogous
  signal is **"`<NN>% ingredients of natural origin`"**, in the `description`/`body_html` prose
  (surfaced as `natural_origin_pct`). Not every product states it (the pure `100% Shea Butter`
  didn't) → `null` = "not stated", don't infer.
- **Full INCI ingredient list** lives in the PDP **HTML**, in the **FIRST**
  `<span class="metafield-multi_line_text_field">` (the **SECOND** such span is the "how to use"
  steps — don't grab it). It's in the *static* HTML (curl gets it; no accordion click needed).

```bash
# price/stock/image/variants (cents), + description prose with "% of natural origin":
curl -s -A "$UA" "https://thebodyshop.ca/products/<handle>.js"
# full INCI ingredient list (FIRST metafield span):
curl -s -A "$UA" -H 'Accept: text/html' "https://thebodyshop.ca/products/<handle>" \
  | grep -oE '<span class="metafield-multi_line_text_field">[^<]*'   # first hit = INCI
```

**Tested extractor:** `scripts/thebodyshop_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-23 on three live products:
- `shea-body-butter` → $10 (compare $26, on sale), 97% natural origin, 200ML + 400ML both in stock,
  full INCI captured.
- `shea-butter-body-butter` (`100% Shea Butter`) → $21, `natural_origin_pct: null` (not stated), in
  stock, 2-ingredient INCI.
- `british-rose-shower-gel-1` → $13, 92% natural origin, **`available: false`** (correctly caught
  the OOS state; the `-POS` suffix in the title flags a point-of-sale/retail-only SKU).
Output per URL: `{handle, url, title, type, vendor, price, compare_at_price, on_sale, available,
image, natural_origin_pct, ingredients, variants:[{title,sku,price,available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-23)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in cents; `variants[].available`; variant `title` = size) |
| % of natural origin | `.js` `description`, regex `(\d{1,3})% ingredients of natural origin` |
| INCI ingredients | PDP HTML, **first** `<span class="metafield-multi_line_text_field">` |
| Image | `.js` `featured_image` (protocol-relative → prefix `https:`) |
| Product URL | `https://thebodyshop.ca/products/<handle>` |
| PDP JSON-LD | present (`Product`, price in dollars, `availability`) — a redundant cross-check for `.js` |

**Failure modes**
- **`.js` vs `.json`**: only `.js` carries the per-variant `available` boolean and the `description`;
  `.json` omits `available`. Use `.js`.
- **TWO `metafield-multi_line_text_field` spans** per PDP: [0] = INCI ingredients, [1] = how-to-use.
  Grabbing the wrong index gives usage steps instead of ingredients. Extractor takes [0].
- **`natural_origin_pct` is often absent** — many products (and pure single-ingredient ones) don't
  state a %. Treat `null` as "not stated", not 0. The INCI list is the reliable ingredient signal.
- Titles sometimes carry a **`- POS`** suffix (point-of-sale / retail-only listing) and are usually
  `available: false` online — trust the `available` flag, not the title.
- JSON-LD `availability` uses BOTH `http://schema.org/...` and `https://schema.org/...` forms in the
  same page; strip the scheme+host when comparing. (The `.js` boolean is simpler — prefer it.)

## Kotn (CA) — Next.js `__NEXT_DATA__` (price/composition/image) + headless-Shopify Storefront GraphQL (per-size stock). No bot wall.

Canada, mid-market DTC essentials — **the strongest natural-fibre source found after Uniqlo**:
almost the entire catalog is 100% long-staple / Egyptian / organic cotton (tees, sweaters,
button-downs, denim, loungewear), plus some linen. A 70% natural-fibre gate passes trivially on most
SKUs. Kids' line is thin/seasonal — this is primarily an adult store. **No bot wall from the VPS** —
plain `urllib` works, no exit node, no Mac delegation. Verified 2026-08-23.

**The architecture (why it takes two sources):** kotn.com is a **custom Next.js/Vercel** front end
(served by Vercel, NOT Shopify — so `/products/<handle>.js`/`.json` and `/products.json` all return
the SPA HTML shell, NOT Shopify JSON). Behind it sits a **headless Shopify store**
(`kotn-ss15.myshopify.com`). Product content is rendered server-side from Sanity CMS into the page's
`<script id="__NEXT_DATA__">` blob; live per-size stock comes from the public Shopify **Storefront
GraphQL** API.

**Which rungs worked:**
- **Rung 4 (SSR JSON in the HTML)** for title, price (CAD), image, colour/size options, and
  **composition** — no click/accordion needed, it's all in `__NEXT_DATA__`.
- **Rung 1 (public JSON API)** for live per-size stock — the Shopify Storefront GraphQL endpoint.

**1. PDP HTML → `__NEXT_DATA__`** (`props.pageProps`):
- `product.title`, `product.shopifyProducts[0].productReferenceV2.store` → `priceRange.minVariantPrice`
  (a **bare number** e.g. `158`, NOT a `{amount,currencyCode}` dict — currency is CAD), `previewImageUrl`
  (a `cdn.shopify.com/...` URL), and `options[]` (`{name:"Colour"|"Size", values:[...]}`).
- `pageProps.shopifyProductID` = the numeric Shopify product id (needed for the GraphQL call).
- **Composition** lives in `product.details[]` — the section whose `detailTitle` starts with `"Fabric"`
  ("Fabric & Care"), inside `detailContent` (Sanity portable-text blocks). Flatten the blocks and pick
  the line naming a fibre/`%` (e.g. `"100% Cotton"`, `"Made from 100% Egyptian cotton yarn. 5GG"`) —
  skip the wash-care line.

**2. Live per-size stock → Shopify Storefront GraphQL**
`POST https://kotn-ss15.myshopify.com/api/2023-01/graphql.json`
header `X-Shopify-Storefront-Access-Token: <token>`. The token is a **public storefront token** baked
into the site's JS bundle (the `pages/_app-*.js` chunk, as `access_token:"<32hex>"` next to
`storefront_uri:"https://kotn-ss15.myshopify.com/api/2023-01/graphql.json"`). Verified token
`bf270532d43fe486e0585779d2c8ae7d` (2026-08-23). **Query by GID, not handle** — the myshopify handle
differs from the kotn.com slug (`product(handle:...)` returns `null`; `node(id:"gid://shopify/Product/<id>")`
works). Returns `variants[].{selectedOptions, availableForSale, quantityAvailable, price}` — real live
inventory counts per size.

```bash
# 1. price/composition/image/options — VPS-side, no auth:
curl -s -A "$UA" "https://kotn.com/products/<handle>" -o pdp.html
#    then parse <script id="__NEXT_DATA__">  (see scripts/kotn_extract.py)
# 2. per-size live stock:
curl -s -X POST "https://kotn-ss15.myshopify.com/api/2023-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Storefront-Access-Token: bf270532d43fe486e0585779d2c8ae7d" \
  -d '{"query":"{ node(id:\"gid://shopify/Product/15190015869296\") { ... on Product { variants(first:100){edges{node{availableForSale quantityAvailable price{amount currencyCode} selectedOptions{name value}}}} } } }"}'
```

**Tested extractor:** `scripts/kotn_extract.py` (pure `urllib`, runs on the VPS). Verified 2026-08-23 on
two live products:
- `mens-relaxed-check-shirt` → "100% Cotton", natural_pct 100, $158 CAD, XS–XL all in stock (12/45/126/109/39).
- `womens-hamatah-sweater` → "100% Egyptian cotton", natural_pct 100, $148 CAD, XS–XL all in stock.
Output per URL: `{url, title, shopify_gid, price, currency, composition, natural_pct, image, colors[],
sizes:[{size, price, quantity, in_stock}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-23)
| What | Where |
|---|---|
| Title / price (CAD, bare number) / image / options | PDP `__NEXT_DATA__` → `props.pageProps.product...store.{priceRange.minVariantPrice, previewImageUrl, options}` |
| Composition (fibre) | `product.details[]` section with `detailTitle`≈"Fabric & Care" → `detailContent` portable-text |
| Shopify product id | `props.pageProps.shopifyProductID` |
| Per-size live stock/price | Storefront GraphQL `node(id:"gid://shopify/Product/<id>")` → `variants[].{availableForSale,quantityAvailable}` |
| Storefront token | `pages/_app-*.js` chunk: `access_token:"<32hex>"` (public; re-scrape if rotated) |
| Product URL | `https://kotn.com/products/<handle>` (discover via `web_search "site:kotn.com <keyword>"` or `/sitemap.xml`) |

**Failure modes**
- **NOT a Shopify front end despite being backed by Shopify.** `kotn.com/products/<handle>.js`, `.json`,
  and `/products.json` all return the Next.js SPA HTML shell (served by Vercel), NOT Shopify JSON. Don't
  waste time on the Shopify convenience endpoints on the `kotn.com` origin — the real Shopify data is
  only reachable via the Storefront GraphQL API on the `kotn-ss15.myshopify.com` origin.
- **Query the Storefront API by GID, not handle.** The myshopify handle (e.g.
  `mens-relaxed-check-shirt-in-pitch-navy-taupe-check`) ≠ the kotn.com slug (`mens-relaxed-check-shirt`),
  so `product(handle:<kotn-slug>)` returns `null`. Use `node(id:"gid://shopify/Product/<shopifyProductID>")`.
- **`priceRange.minVariantPrice` in the SSR blob is a bare integer, not an `{amount,currencyCode}` object**
  — cost the first extractor run an `AttributeError`. Treat it as a number; currency is CAD.
- **Variant references in the SSR blob are unresolved** (`{_ref:"shopifyProductVariant-...", _weak:true}`)
  — SSR carries NO stock/quantity. Stock only comes from the GraphQL call. (grep for `availableForSale`
  in `__NEXT_DATA__` → 0 hits.)
- **Descriptions use "100% Egyptian cotton" prose without a bare `%N` fibre-pair** on some knits — the
  natural-fibre parser must fall back to detecting a named natural fibre + "100%", not only `\d+%\s*fibre`
  pairs. (Handled in `kotn_extract.py::natural_pct`.)
- The public storefront token can rotate; if GraphQL calls 401/error, re-scrape it from the current
  `pages/_app-*.js` chunk (`grep -oE 'access_token:"[a-f0-9]{32}"'`). Price/composition still come from
  SSR even if stock is unavailable.

## IKEA (CA) — rendered-DOM via web_extract (Cloudflare-walled to curl/JSON; NO JSON-LD)

Canada, home/furniture/textiles/kitchenware — the "home" role, and a real natural-fibre
textile source (GURLI/AINA cotton cushion covers, DVALA cotton bedding, VÅRELD, cotton
throws). Confirmed in Sumeet's YNAB history (frequent). Domain **`ikea.com/ca/en`**
(`/p/<slug>-<article>/`). Global IKEA runs the same platform per-market — swap the
`/<cc>/<lang>/` prefix and the recipe should transfer. Verified 2026-08-24.

**Which rung worked: `web_extract` (rendered DOM) — rung 4.** From the VPS *every* cheap
transport is Cloudflare/Akamai-403'd and none is fixable VPS-side:
- `curl`/`urllib` to the PDP, to `/ca/en/products/<article>.json`, to the legacy
  `/iows/catalog/availability/<article>` endpoint, and to `api.ingka.ikea.com/salesitem/...`
  → **all HTTP 403** ("Access Denied" / Cloudflare `__cf_bm` challenge / AkamaiGHost).
- There is **NO `application/ld+json`** block on the PDP (`grep -c` → 0). Don't hunt for one.
But `web_extract` (Crawl4AI headless Chromium) **passes the passive Cloudflare check** and
returns the fully-rendered page carrying name, live price, article no., **Materials/composition**
(critical for the natural-fibre gate), full-res image, and rating — no exit node, no Mac CDP.

**Product URL shape:** `https://www.ikea.com/ca/en/p/<slug>-<article8>/`
e.g. `.../p/gurli-cushion-cover-unbleached-10598777/`. The 8-digit tail is the article id;
it renders on the page as the dotted `NNN.NNN.NN` (`10598777` → `105.987.77`). A STALE/renamed
handle redirects to the **category listing** (still useful — the grid carries current product
URLs + visible prices). Find candidate URLs via `web_search "site:ikea.com/ca/en <product>"` —
snippets even carry the "100% cotton" composition line for textiles.

```bash
# 1. Render the PDP (web_extract tool call — passes Cloudflare):
#      web_extract(urls=["https://www.ikea.com/ca/en/p/<slug>-<article>/"])
#    -> saves full page to ~/.hermes/cache/web/www.ikea.com-<hash>.md
# 2. Parse it:
python3 scripts/ikea_extract.py ~/.hermes/cache/web/www.ikea.com-XXXX.md \
        "https://www.ikea.com/ca/en/p/<slug>-<article>/"
#    -> {url, name, price, currency, article_no, composition, natural_pct,
#        is_textile, image, rating, reviews}
```

**Key fields (verified 2026-08-24 on BILLY bookcase `205.220.46` = furniture, and GURLI
cushion cover `105.987.77` = textile 100% cotton)**
| What | Where in rendered markdown |
|---|---|
| Name | product H1 `# <NAME>, <colour>, [<size>](url)` — unwrap the md link, strip category H1s ("Products", "<Series> bookcases") |
| Price | `Price $ 7.99` label (space-tolerant). No sale strike in the render — shown price IS the live price |
| Article no. | the `NNN.NNN.NN` line right after the series-name block (e.g. `205.220.46`) |
| Composition | `#### Material` block under "Materials and care". Textiles → `100 % cotton` / `55 % linen, 45 % viscose`; furniture → `Particleboard, Paper foil` (no fibre %) |
| natural_pct | sum of natural-fibre % — only meaningful when `is_textile`; `null` for furniture (fibre gate N/A) |
| Image | first `.../images/products/<slug>__<id>_s5.jpg`; parser strips the `?f=` size query for full-res |
| Rating / reviews | `Review: 4.2 out of 5` / `Total reviews: 99` |

**Failure modes**
- **All JSON/API transports 403 from the VPS** (Cloudflare + Akamai) — curl, `products/<id>.json`,
  `iows` availability, `api.ingka.ikea.com`. Don't burn calls; go straight to `web_extract`.
- **NO JSON-LD on the PDP** — unlike most Demandware/SFCC retailers. Data is only in the rendered DOM.
- **Live stock/availability is NOT reliably in the render.** The PDP shows "Delivery: Checking
  availability..." / "Store: Select store" placeholders — the stock reads from a *separate XHR*
  keyed to a postal code that `web_extract` can't fire. So this recipe gives price + composition +
  image reliably, but **stock is unknown** (`in_stock: null`) — verify on the live page (enter a
  postal code) before promising availability, or escalate to CDP for a firm answer. IKEA also runs
  occasional "storefront currently unavailable / checkout not available" banners (seen on one render).
- **The "Complete with" / accessory blocks name their OWN materials** (e.g. an INNER cushion
  "Synthetic fibers" right under a 100%-cotton cover). The parser anchors composition to the FIRST
  `#### Material` block, which is the product's own — don't grab a later accessory's material line.
- **Furniture "Material" is board/foil/veneer, not fibre** — `is_textile` is False and the natural-
  fibre gate simply doesn't apply (a bookcase isn't a fabric). Only gate textiles/soft goods.
- **`%` glued to fibre name is fine** (`100 % cotton` with a space, or `55% linen`) — the parser
  handles both; viscose/rayon still count as SYNTHETIC per the everywhere rule.

## Tilley (CA) — Shopify `.js` (price/stock/variants) + PDP `<h6>Fabric</h6>` composition. No bot wall.

Canada, mid/premium — iconic natural-fibre travel/outdoor brand (100% cotton "Wanderer"/"Airflo"
hats, organic-cotton tees, 100% linen jersey, merino). One of the cleaner natural-fibre sources:
most of the hat + apparel catalog is single-fibre cotton/linen. It's a Shopify store, so the
standard endpoints are open **from the VPS with a plain UA** — no exit node, no Mac CDP.
Verified 2026-08-24.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side `urllib`.**
- **`/products/<handle>.js`** is the money endpoint: `price`/`compare_at_price` (in **CENTS**),
  top-level `available`, and a `variants[]` grid each with `option1`=Colour / `option2`=Size,
  `price`, `compare_at_price`, and a real **`available`** boolean → **per-size/per-colour stock
  directly**. Also `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`),
  `vendor`, `type`, `tags`. (Use `.js`, not `.json` — only `.js` carries `available`.)
- **Composition is NOT in the JSON** (the `.js` `description` is marketing prose). It lives in the
  PDP **static HTML** under a "Fabric, Care & Origin" accordion, anchored by an **`<h6>Fabric</h6>`**
  header. The wrapper after that header **varies by template**:
    - hats: `<div class="specs"><h6>Fabric</h6><p>100% Cotton</p></div>`
    - apparel: `<h6>Fabric</h6>` … loose text / `ewa-rteLine` divs → `100% Linen`
  So anchor on `<h6>Fabric</h6>`, take text up to the next `<h6>`/`Care`/accordion end, strip tags.
  It's in the *static* HTML (no click needed). Some certified-organic tees state fibre only in
  prose ("certified organic cotton", **no %**) — treat composition as a phrase and leave
  `natural_pct` = None when there's no percentage to sum.

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
# price/stock/variants/image (cents):
curl -s -A "$UA" "https://www.tilley.com/products/<handle>.js"
# composition (static HTML — no accordion click needed):
curl -s -A "$UA" -H 'Accept: text/html' "https://www.tilley.com/products/<handle>" \
  | grep -oE '<h6>Fabric</h6>[^<]*(<[^>]+>[^<]*){0,3}'   # e.g. ...100% Cotton / 100% Linen
```

**Discovery** (find handles): `GET /search/suggest.json?q=<terms>&resources[type]=product&resources[limit]=10`
→ `resources.results.products[]` with `title`, `handle`, `url`, `price`, `available`, `image`.
(URL-encode the brackets: `resources%5Btype%5D=product&resources%5Blimit%5D=10`.)

**Tested extractor:** `scripts/tilley_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-24 on four live products:
- `t3-wanderer-hat` → "100% Cotton", natural_pct 100, $99, 12 colours × 10 sizes in stock.
- `ltm6-airflo-sun-hat` → "100% Recycled Nylon. Mesh: 100% polyester", natural_pct 0, $99.
- `linen-jersey-t-shirt` → "100% Linen", natural_pct 100, $90.
- `organic-crew-t-shirt` → "certified organic cotton" (prose, no %), natural_pct None, $28.
Output per URL: `{handle, url, title, vendor, type, price, compare_at_price, on_sale, available,
composition, natural_pct, image, colors[], sizes[], variants:[{color,size,price,compare_at,
available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-24)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in cents; `variants[].available`) |
| Composition (fibre %) | PDP HTML, text after `<h6>Fabric</h6>` (in the "Fabric, Care & Origin" accordion; static) |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`) |
| JSON-LD | PDP has a `Product` block too (`offers[]` per variant, `priceCurrency` **USD**) — but no `material`; use it only as a price cross-check, prefer `.js` |
| Product URL | `https://www.tilley.com/products/<handle>` |

**Failure modes**
- **Hat sizes are fitted (`6 7/8`…`8+`), not S/M/L**, and there are ~100+ variants (colour × head
  size). Dedup colours/sizes for display; rely on per-variant `available`, not the top-level flag.
- **JSON-LD prices are in USD** (`priceCurrency: "USD"`), even on the CA-facing site — do NOT show
  the JSON-LD `price` as CAD. The `.js` `price` (cents) is the storefront (CAD) price; use it.
- **Composition-fallback trap:** a naïve "first `NN% <word>`" match grabs CSS (`100% repeat-x`,
  `width:100%`). Gate the fallback to real textile-fibre words (cotton/linen/nylon/polyester/…);
  the extractor does this, then falls back to a prose fibre phrase (certified-organic tees).
- **"Recycled nylon"/"recycled polyester" is still SYNTHETIC** — recycled ≠ natural. `100% Recycled
  Nylon` is natural_pct 0. (Recycled *cotton* would still count as cotton.)
- No bot wall observed VPS-side (200 on homepage, `.js`, `suggest.json`, PDP HTML). If that ever
  changes, it's a standard Shopify front — the recipe transfers to any Shopify origin.

## Staples (CA) — Shopify `/products/<handle>.js` (Cloudflare guards `.json`/PDP, not `.js`). No Mac needed.

Canada, general-merchandise / office / tech / home-office — office chairs and furniture,
monitors/laptops/peripherals, school and office supplies, some home. Confirmed in Sumeet's
YNAB history. Mostly a **gift / home-office / gap-filler** retailer, **not apparel**, so the
natural-fibre gate is usually **N/A** (a chair or monitor has no fibre %). Verified 2026-08-24.

**Which rung worked: Shopify JSON (rung 2) — all VPS-side, pure `urllib`.** staples.ca is a
Shopify store. The bare PDP and `/products/<handle>.json` are Cloudflare-walled (`403 "Just a
moment..."`), but **`/products/<handle>.js` is NOT** — it returns the full product JSON
(title, price/compare_at in **CENTS**, per-variant `available`, image, and a very rich
`tags[]` array). No exit node, no Mac delegation.

The `tags[]` array is the differentiator vs. a plain Shopify store — it carries structured spec
data Staples flattens into Shopify tags:
- `brand:Office Star`, `model_num:WD387-U6`, `upc_code:090234154761`
- `AverageOverallRating:number:3.4583`, `TotalSubmittedReviews:number:24`
- category breadcrumb `bc_l1_name:...` to `bc_l4_name:...` (Furniture and Home, Office Furniture, ...)
- material/spec attributes as `chair_seat_material_*:Faux Leather`, `chair_upholstery_*:...`,
  `colour_family_*:Black`, `chair_weight_capacity_*:Supports up to 250 lb.` — the extractor
  pulls any `*_material_*`/`*_upholstery_*`/`*_fabric_*`/`*_fill_*` tag into `material`.

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
# money endpoint — price(cents)/compare_at/available/variants/image/tags:
curl -s -A "$UA" "https://www.staples.ca/products/2837129-en-staples-berwood-meshfabric-task-chair.js" | python3 -m json.tool | head
```

**Tested extractor:** `scripts/staples_extract.py` (pure `urllib`, runs on the VPS). Verified
2026-08-24 on three live products — an office chair (`2837129`, $149.99 sale / $199.99, 522
reviews), a faux-leather guest chair (`755550`, Office Star, material "Faux Leather"), and an
ASUS monitor (`3014644`, $179.99 sale / $289.99) — title, price, sale, image, brand, model,
UPC, rating, and category breadcrumb all matched the live pages. Output per URL: `{url, handle,
title, brand, price, compare_at_price, on_sale, available, material[], natural_pct, model, upc,
rating, n_reviews, categories[], image, variants[], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-24)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in CENTS; `variants[].available`) |
| Brand | `tags[]` `brand:<name>` (falls back to `vendor`, which is literally "staples") |
| Model # / UPC | `tags[]` `model_num:<code>` / `upc_code:<digits>` |
| Rating / #reviews | `tags[]` `AverageOverallRating:number:<f>` / `TotalSubmittedReviews:number:<n>` |
| Category breadcrumb | `tags[]` `bc_l1_name:` ... `bc_l4_name:` (in order) |
| Material / upholstery | `tags[]` `*_material_*` / `*_upholstery_*` / `*_fabric_*` value after last `:` |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` prefix `https:`) |
| Product URL | `https://www.staples.ca/products/<handle>` |

**Failure modes**
- **`/products/<handle>.json` and the bare PDP are Cloudflare-walled from the VPS** (`403 "Just a
  moment..."`) — but **`.js` is open**. Always use `.js`; don't waste a call on `.json`/PDP.
- **`/search/suggest.json` is also Cloudflare-blocked** (returns empty body, not JSON) — the usual
  Shopify predictive-search discovery does NOT work here. Discover candidate URLs via
  `web_search "site:staples.ca products <keyword>"`; result URLs are already `/products/<handle>`.
- **Most Staples SKUs have a single `Default` variant** — furniture/electronics aren't sized, so
  `variants[]` is length-1 and `available` is the whole-product stock flag. Colour variants (when
  they exist) come through as `option1` = a raw tag like `chair_colour_8637:Cherry/Black` rather
  than a clean colour word; strip the `key:` prefix for display.
- **`vendor` is always literally `"staples"`** — it's the store, not the brand. Use the
  `brand:` tag for the real manufacturer (Office Star, ASUS, ...); fall back to `vendor` only if
  absent.
- **Not an apparel store** — `material` is usually a construction word ("Mesh/Fabric", "Faux
  Leather", "Wood"), not a fibre %, so `natural_pct` is almost always `null`. That's expected; the
  natural-fibre gate simply doesn't apply to a chair or a monitor.

## MEC (CA) — rendered-DOM via web_extract (headless Next.js over BigCommerce; no JSON-LD, no API)

Canada, outdoor co-op — the "kids, adults, outerwear/base-layer" role and a genuinely
**natural-fibre-friendly** source: deep merino-wool base layers, organic-cotton tees, and
merino/cotton blends across men/women/kids. Fits the household's fitness/outdoor angle. Domain
**`mec.ca`** (`/en/`). Runs on a **headless Next.js storefront over BigCommerce** (store hash
`s-xw5rh7060c`, images on `cdn11.bigcommerce.com`). Verified 2026-08-25.

**Which rung worked: `web_extract` (rendered DOM) — rung 4.** Same class as The Children's Place.
From the VPS, `curl`/`requests` get a hard **Cloudflare 403** (`"Just a moment..."`), and there is
**NO usable `application/ld+json`** on the PDP. But the JS-rendered markdown that `web_extract`
returns carries everything the skill needs: title, sale + original price + %OFF + sale flag, **fibre
composition** (the "Fabric content" tech-spec row — critical for the natural-fibre gate), colours,
sizes, style id, fabric weight, country of origin, and the BigCommerce CDN product image. NO exit
node or Mac delegation needed; mec.ca rendered clean on the FIRST web_extract pass for both test
products (no Akamai-style intermittent block seen). Parse with `scripts/mec_extract.py`.

Verified 2026-08-25 on two live products — prices, %OFF, composition, colours, sizes, made-in, and
the image (which returns `image/png`) all matched the live pages:
- Mountain SS Tee (`6036-412`) → 60% organically grown cotton / 40% recycled polyester,
  natural_pct **60**, $39.95, made in China, S–XXL, 3 colours.
- T2 Merino Base Layer Bottoms (`6019-342`) → 46% merino wool / 35% recycled polyester / 19%
  polyester, natural_pct **46**, $54.94 (was $109.95, 50% OFF, "Last chance"), made in Viet Nam.

**Product URL shape:** `https://www.mec.ca/en/product/<style-id>/<slug>` where `<style-id>` is the
`NNNN-NNN` "Style ID" shown on the page (e.g. `6036-412`). Find candidates via
`web_search "site:mec.ca <category> <keyword>"` — result URLs are already the `/en/product/...` form.

```bash
# 1. Render the PDP (renders clean first pass; no retry/exit-node needed):
#    web_extract(urls=["https://www.mec.ca/en/product/<style-id>/<slug>"])
#    -> saves full page to ~/.hermes/cache/web/www.mec.ca-<hash>.md
# 2. Parse it:
python3 scripts/mec_extract.py ~/.hermes/cache/web/www.mec.ca-XXXX.md \
  "https://www.mec.ca/en/product/<style-id>/<slug>"
#    -> {title, price, original_price, on_sale, pct_off, sale_flag, composition,
#        natural_pct, colors[], sizes[], style_id, made_in, image, fabric_weight}
```

**Key fields (verified 2026-08-25)**
| What | Where in rendered markdown |
|---|---|
| Title | product H1 after the `[MEC](.../brands/mec)\nCompare\n# <Title>` anchor |
| Style ID | `Style ID: 6036-412` (authoritative product id; == URL segment) |
| Regular price | standalone `\n$NN.NN\n` line under the description |
| Sale price + original | `Current price $54.94, original price $109.95~~$109.95~~` |
| % OFF | `50% OFF` line (own line; NOT glued to the price like Children's Place) |
| Sale flag | `Last chance` / `Final sale` / `Clearance` line |
| Composition | tech-spec row `| Fabric content | \n  * 46% merino wool\n  * 35% recycled polyester ... |` |
| Fabric weight | tech-spec row `| Fabric weight | 180gsm |` |
| Made in | tech-spec row `| Made in | Viet Nam |` |
| Colours | swatch bullets between `Colour:<first>` and `Size:` |
| Sizes | glued run after `Size: SelectSize guide` (e.g. `SmallMediumLargeX-LargeXX-Large`) — split on known size tokens |
| Image | `_next/image?url=<pct-encoded cdn11.bigcommerce.com/.../products/<n>/images/<n>/...png>` — decode & prefer the `/products/` path (NOT the `/attribute_value_images/...preview.jpg` swatch) |

**Failure modes**
- **`curl`/`requests` from the VPS → hard Cloudflare 403 (`"Just a moment..."`)** on the PDP.
  Do NOT grind curl or hunt a client-id — go straight to `web_extract`, which renders clean.
- **NO `application/ld+json` on the PDP** — don't waste time grepping for it (there isn't one).
  All structured data is only in the rendered DOM.
- **Per-size STOCK is NOT in the render.** MEC loads delivery/pickup availability from a separate
  XHR only *after* a size is selected — the render shows only "Select a size to see delivery
  availability". So `mec_extract.py` returns sizes but no per-size stock; treat stock as UNKNOWN and
  verify on the live page before recommending. (For a firm per-size answer you'd need the CDP/browser
  path to click each size swatch — not attempted, since composition/price/image were the goal.)
- **Image trap:** the first `cdn11.bigcommerce.com` URL in the markdown is often the 64px colour
  **swatch** (`/images/stencil/.../attribute_value_images/...preview.jpg`), not the hero product
  image. The real image lives under `/products/<n>/images/<n>/...(png|jpg)` and renders ABOVE the
  title — the extractor scans the FULL markdown and prefers the `/products/` path.
- **"recycled polyester" is still polyester (synthetic)** for the fibre gate — the merino base
  layer at 46% merino / 54% (recycled+virgin) polyester is natural_pct **46**, not a wool product.
  MEC leans heavily performance-synthetic (its whole base-layer/rain/insulation range); the
  natural-fibre wins are the **organic-cotton tees**, **merino-dominant** knits, and cotton/hemp
  casual lines. Always read `Fabric content`, don't trust "merino"/"cotton" in the title.
- BigCommerce store hash `s-xw5rh7060c` is stable in image URLs; if the images 404 in future,
  re-derive it from a fresh render.

## ASICS Canada — rendered-DOM via web_extract (Magento/Adobe Commerce, footwear)

Canada, mid/upper athletic footwear + activewear. Confirmed in Sumeet's YNAB history
(his fitness angle). Domain **`asics.com/ca/en-ca`**; runs on Adobe Commerce / Magento
(the "Pearl" theme, Lyonscg/WeltPixel integration). **Footwear → the natural-fibre gate is
N/A** (uppers are engineered mesh/synthetic; no fibre-% is published — same situation as
Crocs). Verified 2026-08-25.

**Which rung worked: `web_extract` (rendered DOM) — rung 4, first-pass clean.**
From the VPS every `curl`/`requests`/`.json` hit is a hard **403** (Akamai-style header
wall — `Attention Required! | Cloudflare` shell). But `web_extract` (Crawl4AI headless
Chromium) renders the PDP cleanly on the **first** call — NO retry loop (unlike Children's
Place's intermittent Akamai), NO exit node, NO Mac delegation. There is **no usable
`application/ld+json`** block and **no open JSON/`.js` API**, so all fields come from the
rendered markdown. Parse with `scripts/asics_extract.py`.

**Product URL shape:** `https://www.asics.com/ca/en-ca/<model-slug>-<styleid>-<color>`
e.g. `.../novablast-5-1011b974-004`. The `<styleid>` is the 7-char Magento style
(`1011b974`) and `<color>` the 3-digit colourway (`004`); together they form the
`Style#: 1011B974.004` shown on the page. Find candidates via
`web_search "site:asics.com/ca <model> running shoe"` — snippets carry the deep URL and
"As low as $NNN" price.

```bash
# 1. Render the PDP (first pass is enough — no retry needed):
#    web_extract(urls=["https://www.asics.com/ca/en-ca/<slug>-<style>-<color>"])
#    -> returns markdown, also cached to ~/.hermes/cache/web/www.asics.com-<hash>.md
# 2. Parse it:
python3 scripts/asics_extract.py ~/.hermes/cache/web/www.asics.com-XXXX.md
#    -> {name, subtitle, price, regular_price, on_sale, availability, in_stock,
#        style_no, style_url_id, rating, review_count, image, url}
```

**Key fields (verified 2026-08-25)**
| What | Where in rendered markdown |
|---|---|
| Name | product `# <NAME>` H1 |
| Subtitle | line after title, e.g. `Men's Running Shoes` |
| Price / sale | `As low as $149.99 Regular Price $190.00` (sale) or `As low as $180.00` (no sale) |
| Availability | `In stock` / `Out of stock` — **overall only, NOT per-size** |
| Style # | `**Style#:**` then `1011B974.004` |
| Rating / reviews | `4.4 out of 5 stars` + `Read 25 Reviews` |
| Image | `https://images.asics.com/is/image/asics/<STYLE>_<COLOR>_SL_LT_GLB?$product$&fmt=png-alpha` (returns `image/png`, 200) |

**Failure modes**
- **VPS is 403-walled on every non-render transport** (`curl`, `requests`, any `.json`/API
  guess). Don't burn time on curl — go straight to `web_extract`, which renders first-pass.
- **Live per-size stock is NOT in the render.** The PDP shows a single overall `In stock`
  line; the size buttons fetch their own availability via an XHR the headless render never
  fires. Fine for this skill (it never orders shoes; adults pick size at checkout) — but do
  NOT claim a specific size is in stock from this data.
- **A 404 renders as a real page** titled `OOPS! THAT PAGE CAN'T BE FOUND.` with a
  `We Recommend` grid of *other* products carrying their own `As low as $NNN` prices — a
  naïve price grab would read a wrong product. The extractor detects the 404 sentinel and
  returns `{error: "404 / product not found"}`. Stale/renamed style URLs 404 → re-derive
  from a fresh `web_search`.
- **No JSON-LD, no Shopify/`.js`, no fibre composition.** Don't grep for `ld+json` (absent)
  or attempt a natural-fibre % (footwear — gate N/A).
- web_extract emits prices with an escaped `\$`; the parser un-escapes before matching.

## Mountain Warehouse (CA) — static-HTML from a plain curl (Next.js over BigCommerce). NO bot wall.

Canada, value-priced outdoor apparel and gear; **natural-fibre-friendly** (lots of 100%
cotton / organic-cotton graphic tees, merino base layers, cotton fleece). Domain
**`mountainwarehouse.com/ca`** (`/ca/fr/` for French). It's a Next.js front over
BigCommerce (store `s-nb5it5hcrj`), but — unusually — **every field the skill needs is
baked into the STATIC HTML** returned by a plain `curl`/`urllib` GET. Verified 2026-08-26.

**Which rung worked: plain `urllib` GET (below rung 1) — NO bot wall, NO render, NO XHR,
NO CDP, NO exit node.** The homepage and PDPs return `200` to a vanilla curl (contrast
Canadian Tire / Michaels / Party City / Marks, all `403` from the VPS). The visible
DOM (not the RSC/JSON-LD, which is present but multiply-escaped and painful) carries
title, sale+was price, %off, full fabric composition, og:image, and **per-size stock**.

**The data, in the static HTML:**
- **Price**: an `aria-label="Original Price: $39.99, Price: $11.99, You save 70%"` on the
  price container gives sale price, was-price, and %off in one shot. Not-on-sale products
  give a bare `aria-label="Price: $X"`.
- **Composition**: `<h3>Fabric Composition</h3><p>Main fabric: Cotton (organic) 100%, Rib:
  Cotton (organic) 97%, Elastane 3%</p>`. **The string chains multiple sections** (`Main
  fabric: ... , Rib: ... , Lining: ...`), each summing to ~100 — so naively summing natural
  fibres across the WHOLE string double-counts (gave `natural_pct: 197`). Fix: isolate the
  `Main fabric:` section (up to the next `Rib/Lining/Trim/...` keyword) before summing.
- **Per-size stock**: each size is a `<input ... class="...VariantOption_radioInput..." [disabled=""]/>
  <label title="Small">S</label>`. A `disabled=""` on the input === that size is OUT OF STOCK.
  Confirmed correct: on `038538` exactly 4 sizes carry `disabled` (XXS, XS, 3XL, 4XL) and
  the extractor flags precisely those. (Colour swatches use a *different* class,
  `Option_radioInput` / `Option_radioLabel`, and carry a per-colour price span.)
- **Image**: `property="og:image"` — a BigCommerce `cdn11.bigcommerce.com/s-nb5it5hcrj/...`
  stencil URL. Returns `image/webp 200` (verified) even though the URL ends `.jpg`.
- Overall availability also sits in the embedded (escaped) JSON-LD `Offer` (`InStock`).

**Tested extractor:** `scripts/mountainwarehouse_extract.py` (pure `urllib`, VPS-side).
Verified 2026-08-26 on two live products:
- `038540` Mountain Explorer Tee → `Main fabric: Cotton (organic) 100%`, natural_pct **100**,
  $11.99 (was $39.99, 70% off), XXS+4XL OOS, rest in stock.
- `038538` Bike Tee → `Cotton (organic) 92%, Polyester 8%`, natural_pct **92**, $11.99,
  XXS/XS/3XL/4XL OOS. Both image URLs return `image/*`.
Output per URL: `{url, title, price, was_price, save_pct, composition, natural_pct, image,
availability, sizes:[{size,in_stock}], colours:[{name,price}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-26)
| What | Where |
|---|---|
| Price / was / %off | `aria-label="Original Price: $X, Price: $Y, You save Z%"` |
| Composition (fibre %) | `<h3>Fabric Composition</h3><p>...</p>` — use the `Main fabric:` section only |
| Per-size stock | `<input class="...VariantOption_radioInput..." [disabled=""]/><label title="...">SZ</label>` |
| Image | `<meta property="og:image" content="...cdn11.bigcommerce.com/s-nb5it5hcrj/...">` |
| Product URL | `https://www.mountainwarehouse.com/ca/p/<6-digit>/mw/<slug>/` |
| Find candidates | `web_search "site:mountainwarehouse.com/ca <category> <keyword>"` (snippets carry the `100% cotton` line + direct PDP URL) |

**Failure modes**
- **Fabric-composition double-count**: the string chains `Main fabric / Rib / Lining` sections,
  each ~100% — sum ONLY the `Main fabric:` section, or you get a bogus >100 natural_pct.
- The Next.js RSC payload and the JSON-LD are BOTH present but **multiply backslash-escaped**
  (`\\\\\"`) — don't try to `JSON.parse` them; read the visible DOM attributes instead
  (aria-label, `disabled=""`, og:image). Far simpler and it's all there.
- Colour swatches vs size swatches use different classes (`Option_*` vs `VariantOption_*`) —
  don't conflate; only the `VariantOption` inputs carry per-size `disabled`.
- Live per-size stock IS reliable here (unlike MEC/ASICS/IKEA where it needs an XHR) because
  `disabled` is rendered server-side into the static HTML.

## Mark's (CA) — CDP Network-intercept of the app's own product XHR (Canadian Tire/FGL stack)

Canada, mid-market workwear/casual basics — **natural-fibre-friendly**: house brands **Denver
Hayes** (heaps of 100% cotton tees/henleys/woven shirts, cotton chinos) and **WindRiver**
(cotton-rich flannels, 98% cotton / 2% spandex stretch flannel). YNAB-candidate. Domain
**`marks.com`** (`/en/pdp/...`). Same **Canadian Tire / FGL "Nucleus"** platform as **Sport Chek**
— so the VPS wall and the fix mirror that recipe. Verified 2026-08-26.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3, but by NETWORK INTERCEPTION, not fetch replay.**
From the VPS *everything* is hard-Akamai-403 (`edgesuite.net` "Access Denied"): `curl` on the root,
on `/products.json`, and on the product API all 403. `web_extract` (Crawl4AI headless) renders
ONLY the footer/nav chrome — the PDP is a client-side SPA that hydrates product data from XHR, so
price/composition/stock never appear in the rendered markdown. So: Mac CDP.

**The two money XHRs the PDP fires (both same-origin, `www.marks.com`):**
- `GET /api/v1/product/api/v2/product/productFamily/<id>?baseStoreId=MKS&lang=en_CA&storeId=392`
  → `name`, `brand.label`, `images[].url`, and `skus[]` where each sku has:
  - `specifications[]` — the **composition** lives here as pairs
    `primary_fabric_1_cd` (e.g. `" Cotton"`) + `primary_fabric_1_percentage_amt` (e.g. `" 100"`),
    repeating `_2_`, `_3_` for blends. Values are space-padded — `.strip()` them. Also `fit_cd`,
    `neckline_style_cd`, `colour_group_cd`, `gender_cd`.
  - `optionIds[]` — the size/colour of THAT sku: `SIZE_CD_4X_LARGE`, `SECOND_SIZE_RANGE_CD_TALL`,
    `COLOUR_GREEN`.
- `GET /api/v1/product/api/v2/product/sku/PriceAvailability?lang=en_CA&storeId=392&cache=true&pCode=<id>&isLoyaltyUser=false`
  → `skus[]` each: `currentPrice.value`, `originalPrice.value`, `isOnSale`, `saleCut`,
  `isUrgentLowStock`, and **live stock** at `fulfillment.availability.Corporate.Quantity`.

Join the two arrays on sku `code`. `<id>` = the style id ending in `f`, tail of the PDP URL
(`.../<slug>-12597467f.html`).

**CRITICAL — intercept, do NOT replay.** The page's own calls return **200** using cookie/edge
auth. Replaying either URL with a same-origin `fetch()` from the page context returns **401**
("missing subscription key"), and adding the APIM key (`subscription-key=c01ef3612328420c9f5cd9277e815a0e`,
liftable from the PDP image URL's `subscription-key=` param) only moves it to **400/404** — the app
injects a further header the replay lacks. So the reliable rung is **CDP `Network.enable` +
`Network.getResponseBody`**: navigate the PDP, watch `Network.responseReceived` for URLs containing
`/product/productFamily/` and `PriceAvailability`, and pull their bodies. `scripts/marks_extract.py`
does exactly this.

**Tested extractor:** `scripts/marks_extract.py` (base64-ship to the Mac; run under the CDP venv,
same launch recipe as `sportchek`/`carters`). Verified 2026-08-26 on three live PDPs:
- `12597467f` Denver Hayes 50-Wash crew tee → 100% Cotton, natural_pct 100, $19.99, 180 variants, in stock.
- `71223583f` Denver Hayes chest-pocket tee → 100% Cotton, natural_pct 100, $19.99, 117 variants, in stock.
- `84350932f` WindRiver stretch flannel → 98% Cotton, 2% Spandex, natural_pct 98, $14.88 on sale, OOS clearance (2 variants).
Image URL verified `image/jpeg` 232 KB (no hotlink block). Output per URL:
`{url, id, name, brand, image, composition, natural_pct, currency, price, price_max, on_sale,
variants:[{sku,size,second_range,colour,price,original_price,on_sale,qty,in_stock,urgent_low}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-26)
| What | Where |
|---|---|
| Name / brand / images / specs / size-colour | `productFamily/<id>` → `name`, `brand.label`, `images[].url`, `skus[].specifications[]`, `skus[].optionIds[]` |
| Composition (fibre %) | `specifications[]` pairs `primary_fabric_N_cd` + `primary_fabric_N_percentage_amt` (space-padded → strip) |
| Price / sale / live stock | `PriceAvailability?pCode=<id>` → `currentPrice.value`, `originalPrice.value`, `isOnSale`, `fulfillment.availability.Corporate.Quantity`, `isUrgentLowStock` |
| Product id | tail of PDP URL: `-([0-9]+f)\.html` |
| Find candidates | `web_search "site:marks.com/en/pdp <brand> <keyword>"` (snippets carry the PDP URL + Product Details) |

**Failure modes**
- VPS Akamai hard-403 on *every* transport (curl/root, `/products.json`, product API). Not
  intermittent (unlike Children's Place Akamai) — don't retry, go straight to Mac CDP.
- **Do not replay the product XHR with `fetch()`** — 401 without the APIM key, 400/404 with it. The
  app adds an extra header; only `Network.getResponseBody` interception gets the real 200 body.
- Fabric spec values are **space-padded** (`" Cotton"`, `" 100"`) — strip before use.
- Big products have colour×size×tall/regular = **100+ skus**; dedup for display, rely on per-sku
  `Corporate.Quantity` for stock, not a top-level flag.
- A `$14.88`-type price with only 2 remaining variants and `isOnSale` is **sold-out clearance**,
  not a bargain (the everywhere-rule) — check `any_in_stock` and `Quantity` before recommending.
- `productFamilyList` (a "you may also need" carousel) also fires — ignore it; it's cross-sell, not
  the current product.

## Sephora (CA) — rendered buy-box via web_extract (name + price only; PARTIAL). API Akamai-walled.

Canada, prestige beauty/personal-care — a **gift-track** store (makeup, skincare, fragrance,
haircare), confirmed household-relevant. Cosmetic, so the **natural-fibre gate is N/A**. Domain
`www.sephora.com/ca/en`. Verified 2026-08-27.

**Which rung worked: `web_extract` rendered DOM — rung 4, and only PARTIAL.** The clean data path
(the product API) is walled from the VPS, and the render is thin:
- Product API `GET /api/v3/catalog/products/<PID>?countryCode=CA&loc=en-CA` (and `/api/v2/…`) →
  **Akamai `403 Access Denied`** from the VPS. `/api/catalog/products/<PID>` → `302`. No VPS-side fix
  (it's a passive fingerprint wall; an exit node won't help — would need Mac CDP + same-origin fetch).
- `curl` on the PDP homepage returns `200` but the PDP HTML has **no usable `application/ld+json`**
  and no `__NEXT_DATA__` product block — the buy-box hydrates from the (walled) XHR.
- **`web_extract` (Crawl4AI headless) renders the buy-box** and reliably yields **product name, list
  price, and the sale/Auto-Replenish price + % off**. It does NOT capture the **image, full INCI
  ingredient list, rating count as a clean number, or per-variant stock** — those load from a
  separate XHR and are absent from the markdown. So: good enough to price a gift candidate and link
  it; escalate to CDP/browser XHR-intercept if you need the image or ingredients.

**Product URL shape:** `https://www.sephora.com/ca/en/product/<slug>-P<6-digit-id>`
e.g. `.../product/ultra-repair-cream-intense-hydration-P381145`. The `P<digits>` id is the SKU
family. Find candidates via `web_search "site:sephora.com/ca/en/product <brand> <keyword>"`.

```bash
# 1. Render the PDP (retry on Akamai — see failure modes):
#    web_extract(urls=["https://www.sephora.com/ca/en/product/<slug>-P<id>"])
#    -> returns markdown inline; long pages also save to ~/.hermes/cache/web/www.sephora.com-<hash>.md
# 2. Parse it (also accepts stdin via "-"):
python3 scripts/sephora_extract.py ~/.hermes/cache/web/www.sephora.com-XXXX.md
#    -> {name, brand, list_price, sale_price, pct_off, on_sale, size, url, source}
```

**Key fields (verified 2026-08-27)**
| What | Where in rendered markdown |
|---|---|
| Name | the product `# ` H1 that does NOT end in `\| Sephora` (first H1 is a `<title>` echo) |
| Brand | best-effort: trailing segment after ` - ` in the `<title> \| Sephora` line |
| List price | first bare `$NN.NN` in the buy-box (often glued: `$28.00or 4 payments…`) |
| Sale price + %off | `get it for $NN.NN (N% off)` (Auto-Replenish) or `$NN.NN (Save N%) $LIST` |
| Size | `Size: 2 oz/56.7 mL` |
| Image / INCI / stock | **NOT in the render** — hydrates via walled XHR; needs CDP |

**Failure modes**
- **Akamai on `web_extract` is INTERMITTENT** (like Children's Place, unlike Carter's/Mark's): a call
  can come back `"Blocked by anti-bot protection: Akamai block"` or a transient
  `CRAWL_LIVECRAWL_TIMEOUT`/`CRAWL_UNKNOWN_ERROR` — **just retry the same URL**; a 2nd/3rd pass renders.
  No exit node or Mac delegation needed for the name+price fields.
- **web_extract mangles UTF-8** in the render: `®` → `Â®`, em/en-dashes → `â…`. The extractor strips
  the stray `Â` and normalises the mangled dashes; do the same if parsing by hand.
- **The first `# ` H1 is a `<title>` echo** (`<name> | Sephora`), not the product H1 — anchor name
  extraction on the first H1 that does NOT end in `| Sephora`.
- Product **API is Akamai-403 from the VPS on every version** — do not burn time on `/api/v3` or
  `/api/v2`; they will not open VPS-side. Image + ingredients require Mac CDP (same-origin fetch of
  the API from a loaded tab) — out of scope for a bounded VPS recon run.

## Brilliant Earth (CA) — rendered-DOM via web_extract (GIFT track: fine jewelry)

Canada/US, ethical fine jewelry — engagement/wedding rings, necklaces, earrings, bracelets.
A **gift-track** retailer (a real Sumeet past purchase). There is NO textile fibre content here:
"composition" is the precious METAL (14K/18K gold, platinum) + gemstone, so the **natural-fibre
gate is N/A** — don't try to compute a fibre %. Verified 2026-08-28.

**Which rung worked: `web_extract` (rendered DOM) — rung 4.** `curl`/`requests` from the VPS hit a
Cloudflare **403 "Brilliant Earth - Verifying"** wall (615 KB challenge shell, 0 JSON-LD). But
`web_extract`'s headless Crawl4AI renders the PDP **clean on the first pass** (like MEC/ASICS —
no retry needed, unlike Children's Place). No JSON-LD, no public Shopify/JSON API found — parse the
rendered markdown with `scripts/brilliantearth_extract.py`.

**CRITICAL — use the `/en-ca/` path for CAD prices.**
- `https://www.brilliantearth.com/en-ca/<Slug>-<STYLE>/` → price renders as **`CAD 1,065`** (what
  Sumeet pays). ALWAYS use this for his carts.
- Bare `.com/<Slug>-<STYLE>/` (US) → price renders in **USD**, and design-your-own settings show
  `$795 (Setting Only)`.

**FINISHED piece vs DESIGN-YOUR-OWN setting** (the single most important distinction here):
- **Finished piece** (birthstone pendant, hoops, studs, pearls, tennis chain) → ONE fixed price +
  an **`ADD TO BAG`** button → buyable as-is. `is_setting_only=False`.
- **"Design your own" setting** (an engagement-ring / pendant / stud SETTING) → shows
  `$N (Setting Only)` + a **`CHOOSE THIS SETTING`** button; the real total depends on the centre
  diamond you separately select. `is_setting_only=True` → this is NOT a single buyable price. For a
  gift cart, prefer finished pieces; if you use a setting, flag it ("setting only; centre stone extra").

**Product URL shape:** `https://www.brilliantearth.com/en-ca/<Descriptive-Slug>-<STYLE>-<numeric>/`
e.g. `.../Lab-Alexandrite-and-Diamond-Birthstone-Pendant-Necklace-14K-Gold-BE4DLCAL376/`. The
`Style: BE...-<metal>` line in Product Details is authoritative. Find candidates via
`web_search "site:brilliantearth.com <category> <keyword>"` — snippets carry direct PDP links.
Metal variants are separate URLs (each metal = its own STYLE-<metal> + numeric id).

```bash
# 1. Render the PDP (en-ca for CAD):
#    web_extract(urls=["https://www.brilliantearth.com/en-ca/<Slug>-<STYLE>/"])
#    -> saves to ~/.hermes/cache/web/www.brilliantearth.com-<hash>.md
# 2. Parse it:
python3 scripts/brilliantearth_extract.py ~/.hermes/cache/web/www.brilliantearth.com-XXXX.md
#    -> {title, price, currency, is_setting_only, in_stock, ship_by, metal, style,
#        gemstone[], chain_length, image, url}
```

**Key fields (verified 2026-08-28)**
| What | Where in rendered markdown |
|---|---|
| Title | the product `# ` H1 (not `## `/`#### ` nav, not the `Brilliant Earth`/`Choose`/`Privacy` H1s) |
| Price (CAD) | `CAD 1,065` on `/en-ca/` finished pieces; `$N (Setting Only)` on US settings |
| In stock / ship | `ADD TO BAG` (finished) or `CHOOSE THIS SETTING` (setting); `ships by <date>` |
| Metal | `Metal:` bullet (`14K Yellow Gold`, `18K White Gold`, `Platinum`) |
| Style id | `Style: BE...-14KY` (base before the `-<metal>` = the slug id) |
| Gemstone | `Type: Lab Grown Alexandrite` / `Type: Diamond` bullets under Details |
| Chain length | `Chain Length: 18 in.` (necklaces) |
| Image | `https://image.brilliantearth.com/media/product_images/<XX>/<STYLE>_..._top.jpg` — CDN is NOT walled (curl returns real `image/jpeg` bytes; safe to hotlink in the email) |

**Failure modes**
- `curl`/`requests` → Cloudflare **403 "Verifying"** on every PDP (title `Brilliant Earth - Verifying`,
  ~615 KB, 0 JSON-LD). Do NOT retry curl; go straight to `web_extract` (renders clean first pass).
- **No JSON-LD and no public JSON/Shopify API** found on the PDP — don't waste time grepping for
  `application/ld+json` or trying `/products/<h>.json`. The rendered markdown is the only source.
- **Design-your-own galleries render BEFORE the product H1**, so their thumbnails sit outside the
  post-H1 slice. Anchor the hero image on the **style-base filename** (`<STYLE>_..._top.jpg`), which
  is unique across the doc — the extractor searches the whole doc for that, not just after the H1.
- A naïve "first URL with a capitalised slug" grabs the `gift-certificate-BEGC` promo link, not the
  PDP. Anchor the product URL on the **style base** too (extractor does this).
- Bare `.com` gives USD; **only `/en-ca/` gives CAD**. Don't email a US price as if it were CAD.
- `brand` is always "Brilliant Earth" (house) — label manually.

## Decathlon (CA) — CDP Chrome on the Mac; composition hides behind a collapsed accordion

Canada, value sports/outdoor (in-house brands Domyos = fitness, Quechua = hiking, Kalenji = run,
Kipsta = team). Kid + adult coverage. Natural-fibre-relevant: the plain "Essentials"/"Essentiel"
cotton tees & sweats — but **the naming lies about the blend**, so read the % every time (a product
literally titled "Cotton Sweatshirt" with `Main Material: Polyester` came back 41% cotton / 59%
polyester — a 70%-rule FAIL). Verified 2026-08-29.

**Which rung worked: CDP windowed Chrome on the Mac — rung 3 (bot-wall bypass).**
- `curl`/`requests` and *every* API guess (`/api/...`, `.json`, `apim`, `graphql`, `api.decathlon.com`)
  → hard Cloudflare **403 "Just a moment..."** from the VPS. No VPS-side fix; exit node won't help
  (fingerprint wall, not IP).
- `web_extract` (Crawl4AI) **does** render the PDP shell — name, brand, visible `$NN.NN` price, star
  rating + review count, `ID <productId>`, care instructions, "Get the bundle" cross-sells. **But it
  is only PARTIAL**: the fibre **composition** sits inside a *collapsed* "Specifications" accordion
  that web_extract never expands, and it returns no image URL and no per-size stock. So web_extract
  alone fails the natural-fibre gate — you must open the accordion, which needs a real browser.
- **Mac CDP is the recipe**: navigate, wait ~13 s (render + Cloudflare auto-clear), click every
  button/summary whose text matches `specification|description|material|composition`, wait ~2.5 s,
  then read the spec table + a body-text fibre regex. `www.decathlon.ca` loads clean over CDP; NO
  interactive press-and-hold.

**The data, once specs are expanded:**
- **Composition**: not in JSON-LD; it's in the expanded "Specifications" block as plain-text
  `100.0% Cotton` / `97.0% Cotton, 3.0% Elastane` lines. Regex the body for
  `(\d{1,3}(?:\.\d+)?\s?%)\s*(cotton|polyester|elastane|wool|linen|...)`. **Guard the decimals** —
  a `\d{1,3}%` regex reads `100.0%` as `0%`. Sum natural fibres (cotton/wool/linen/silk/lyocell).
- **Price**: JSON-LD `offers` is usually **empty** (`offers: []`); use the visible `$NN.NN` on the
  buy box instead. Rating comes through JSON-LD `aggregateRating.ratingValue` fine.
- **Image**: JSON-LD `image` and `og:image` are both empty. Real photos are `<img>` src on
  `contents.mediadecathlon.com/pNNNNNN/k$<hash>/picture.jpg?format=auto&f=320x0` — bump `f=320x0`
  to `f=650x0` for the email thumb. This CDN is **NOT walled** (curl returns `image/jpeg` from the
  VPS directly — safe to hotlink; verify bytes first).
- **specs{}** also carries `Main Material`, `Cut`, `Collar Type`, `Skill Level`, `Frequency`, plus an
  environmental-impact %-breakdown (`Raw material`, `Use`, ...) — the latter are NOT fibre content.

**Tested extractor:** `scripts/decathlon_extract.py` (base64-ship to the Mac, run under the CDP
venv). Verified 2026-08-29 on two live PDPs — Fitness T-Shirt Essentials 500 = 100% cotton main body
(PASS), Cotton Sweatshirt 500 Essentiel = 41% cotton/59% poly (FAIL 70%). Name, brand (Domyos),
price, rating, composition, and mediadecathlon image all matched the live pages.

**Product URL shape:** `https://www.decathlon.ca/en/p/<slug>/<modelId>/c...m<productId>` (the trailing
`m<productId>` = the `ID` shown on the PDP; `.../en/p/<productId>/<slug>` also resolves). Discover via
`web_search "site:decathlon.ca <category> <keyword>"`.

**Failure modes**
- Hard Cloudflare 403 on every VPS transport incl. all API guesses — don't grind curl/exit-node.
- `web_extract` gives price/name/rating but **NOT composition/image/stock** — treat it as a partial
  first pass only; escalate to Mac CDP for the fibre gate.
- Decimal-eating regex (`\d{1,3}%` → `0%` on `100.0%`) — allow `(?:\.\d+)?`.
- Product names/`Main Material` are misleading ("Cotton Sweatshirt" that's mostly poly) — always
  read the actual `%`. Domyos athleisure skews synthetic; the plain cotton "Essentials" tees are the
  clean natural-fibre picks.
- JSON-LD `offers` empty and `image` empty — use visible price + mediadecathlon `<img>` src.
- **Per-size live STOCK not captured** — it hydrates via XHR after a size click; the render/JSON-LD
  don't carry it. Verify size availability on the live page (or extend the script to click swatches).

## Everlane — Shopify `.js` (price/stock/variants) + PDP-HTML Materials accordion. No bot wall. ⚠️ USD.

US-based (ships to Canada); mid/premium essentials. **One of the strongest natural-fibre sources**
found: deep 100% organic-cotton tee/knit lines, 100% cashmere/merino sweaters, linen, and denim —
cotton/cashmere/wool/linen lines routinely clear a high natural-fibre gate. It's a **Shopify store**
(`powered-by: Shopify`), so **no bot wall from the VPS**: plain `urllib`/`curl` work for both the
`.js` endpoint and the PDP HTML. No exit node, no Mac delegation. Verified 2026-08-29.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.**
- **`/products/<handle>.js`** is the money endpoint: `title`, `type`, `vendor`, `price`/
  `compare_at_price` (in **CENTS, USD**), top-level `available`, and a `variants[]` grid each with
  `title` (size, or `waist / inseam` for bottoms), `price`, `compare_at_price`, and a real
  **`available`** boolean → **per-size stock directly**. `featured_image` is protocol-relative
  (`//cdn.shopify.com/...` → prefix `https:`).
- **Composition is NOT in the `.js`** (only a coarse `tags: ["fabric: cotton"]`). Exact percentages
  live in the **PDP HTML**, in a *static* materials accordion:
  `<div ... class="ProductAccordion-Materials--...">Materials:<ul><li>100% Organic Cotton</li></ul>`.
  No click/JS needed — `curl` gets it. One or more `<li>` (e.g. `100% Cashmere (50% Recycled)`,
  `94% Cotton, 6% Elastane`). Sum the natural `%` and gate.
- **JSON-LD** on the PDP is a `ProductGroup` with per-variant `offers` (`price`, `priceCurrency`,
  `availability`) — a fine cross-check, but the `.js` already carries everything and is simpler.

```bash
# price/stock/variants/image (cents, USD):
curl -s -A "$UA" "https://www.everlane.com/products/<handle>.js"
# exact composition (static HTML, no click):
curl -s -A "$UA" -H 'Accept: text/html' "https://www.everlane.com/products/<handle>" \
  | grep -oiE 'Materials:<ul>.*?</ul>'   # -> Materials:<ul><li>100% Organic Cotton</li></ul>
```

**Tested extractor:** `scripts/everlane_extract.py` (pure `urllib`, runs on the VPS). Verified
2026-08-29 on three live products — 100% organic-cotton crew (natural_pct 100, 6/6 sizes in stock),
100% cashmere crew (natural_pct 100, only **1/7** sizes buyable — per-size stock discriminates
correctly), and a 94% cotton / 6% elastane performance chino (natural_pct 94, on sale $35 from $118).
Output per URL: `{url, handle, title, type, vendor, price_usd, compare_at_usd, on_sale, available,
composition, natural_pct, image, colors[], sizes[], variants:[{color,size,price_usd,compare_at_usd,
available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-29)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in **cents, USD**; `variants[].available`) |
| Composition (fibre %) | PDP HTML, `Materials:<ul><li>…</li></ul>` in a static `ProductAccordion-Materials` div |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`) |
| Catalog listing | `/products.json?limit=250&page=N` (full catalog, paginated) |
| Product URL | `https://www.everlane.com/products/<handle>` |

**Failure modes**
- **⚠️ PRICES ARE USD, not CAD.** `Shopify.currency.active == "USD"` and JSON-LD `priceCurrency ==
  "USD"` even though Cloudflare serves the CA edge (`country;desc="CA"`). Convert to CAD for Sumeet's
  cart or label the price USD explicitly — do NOT drop a USD number into a CAD cart. This is the single
  non-obvious trap here (same class as Tilley, whose JSON-LD prices were USD).
- **`suggest.json` came back empty** for keyword queries — don't rely on it for discovery. Use
  `web_search "site:everlane.com/products <keyword>"` (snippets carry the composition prose and the
  `/products/<handle>` URL) or page `/products.json`.
- **One handle per colourway.** Colour isn't a variant option here — each colour is a separate handle
  (e.g. `...-crew-black`, `...-crew-white`). `variants[]` iterate SIZE only. To price a colour range,
  fetch each colour's handle.
- **Bottoms use a `waist / inseam` variant title** (`32 / 28`) and can have 40+ variants — dedup and
  rely on per-variant `available`, not the top-level flag (a product can be `available:true` with only
  3/44 sizes buyable).
- **`elastane`/`spandex`/`polyester`/`nylon`/`viscose`/`modal` are SYNTHETIC** per the fibre rule.
  Everlane's ReNew fleece, Performance/tech, and activewear lines are predominantly recycled
  poly/nylon — read the Materials `%`, don't trust an "organic"/"cotton" product name. A 94% cotton /
  6% elastane chino is natural_pct 94 (clears 70%); a ReNew fleece is ~0.
- Recycled cotton/wool/cashmere still count as natural fibre (`100% Cashmere (50% Recycled)` = 100).

## Quince (CA) — JSON-LD `ProductGroup` (price/stock/image) + `__NEXT_DATA__` `details` (fibre %). NO bot wall.

Canada (`/ca/` gives CAD), DTC "affordable luxury". **One of the strongest natural-fibre
sources found** — deep 100% organic-cotton, Mongolian cashmere, European linen, mulberry silk,
merino/alpaca lines across women / men / kids / home (bedding, towels). Verified 2026-08-30.

**Which rung worked: static HTML from a plain `urllib`/`curl` GET — no rung-3 needed.**
`www.quince.com/ca/...` returns 200 to a plain UA GET (curl and `web_extract` both fine); the
PDP embeds everything. NO Cloudflare/Akamai/PerimeterX wall from the VPS. Two blocks carry it:

- **JSON-LD `@graph` → `ProductGroup.hasVariant[]`** — one entry **per colour × size** with
  `offers.price`, `offers.priceCurrency` (**CAD on `/ca/`**), `offers.availability`
  (`InStock`/`OutOfStock`), `image`, `sku`, `color`, `size`. This is price + **per-variant stock**
  + image directly. (The JSON-LD is the SECOND ld+json block; the first is `BreadcrumbList`. The
  Product block is nested under `@graph`, so a naïve "parse the first ld+json" grabs the crumbs —
  iterate blocks and pick the one with `@graph`.)
- **`__NEXT_DATA__` → `props.pageProps.pageData.context.pageDataJson.product`** — the **exact fibre
  composition** lives in `product.details` (HTML `<ul><li>Made from 55% linen, 45% cotton…</li></ul>`).
  The JSON-LD `material` and the loose `product.material` label are **marketing text only**
  ("Organic Cotton", "Cotton/Modal") — do NOT gate on them; parse the `%` out of `details`.

```bash
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
curl -s -A "$UA" "https://www.quince.com/ca/women/<handle>" -o page.html
python3 scripts/quince_extract.py page.html   # or pass the URL directly (urllib-fetches)
# -> {name, material_label, composition, natural_pct, image, currency, price_min/max,
#     colors[], sizes[], variants:[{color,size,price,availability,sku}], any_in_stock, rating}
```

**Product URL shape:** `https://www.quince.com/ca/<gender>/<handle>` e.g.
`/ca/women/100-organic-cotton-sweater-tee`. Some handles sit under a sub-path
(`/ca/women/tees/cotton-modal-crew-neck-tee`) — take the exact URL from a
`web_search "site:quince.com/ca <keyword>"` result, don't hand-build (a wrong guess 404s).

**Selectors / fields** (verified 2026-08-30)
| What | Where |
|---|---|
| Per-variant price / stock / image / sku | JSON-LD `@graph` → `ProductGroup.hasVariant[].offers` (+ `.image`) |
| Currency | `offers.priceCurrency` = `CAD` on `/ca/` (would be `USD` on the bare `/` US site) |
| **Exact fibre composition** | `__NEXT_DATA__ …product.details` HTML `<li>…NN% fibre…</li>` |
| Loose material label (do NOT gate on) | `…product.material` / JSON-LD `material` |
| Rating / review count | JSON-LD variant `aggregateRating` |
| Image host | `images.ctfassets.net/...` (Contentful CDN) |

**Failure modes**
- **The product NAME lies about fibre content.** "Cotton Modal Scoop Neck Tee" is **50% cotton /
  50% modal** → natural_pct **50** (modal is semi-synthetic; count synthetic). "Lightweight Cotton
  Cashmere … Tee" came back **65% cotton / 32% ecovero / 3% cashmere** → natural_pct **68**, which
  FAILS a 70% rule despite "cotton cashmere" in the name. Branded viscose (LENZING **EcoVero**,
  modal, Tencel/lyocell) is counted synthetic per the skill default — always read the `%` from
  `details`, never the title or `material` label.
- JSON-LD Product block is nested under `@graph` and is the 2nd ld+json script (1st = breadcrumbs).
- Prices on the bare `/` (US) site are **USD**; always use the `/ca/` path for CAD.
- Live stock IS in the render (JSON-LD `availability` per variant) — unlike the Next.js/BigCommerce
  retailers (MEC/Mountain Warehouse) where stock hides in an XHR. All sizes InStock on the tees
  tested; the field discriminates OutOfStock correctly per SFCC convention.
- `web_extract` also renders it clean (rung-4 fallback), but the plain `urllib` GET is faster and
  gives the raw JSON — no need to escalate.

## Province of Canada — Shopify `.js` (price/stock) + `.json` body_html (composition). No bot wall.

Canada, DTC — **made-in-Canada basics, heavy on organic/GOTS cotton** (Monday Tee, fleece,
denim shirts). A strong natural-fibre source: staple tees are 100% GOTS-certified organic cotton;
fleece is typically 80% cotton / 20% polyester (passes a 70% gate). Standard Shopify store, **NO
bot wall** from the VPS — plain `curl`/`urllib` work, no exit node, no Mac. Verified 2026-08-30.

**Which rung worked: Shopify JSON (rung 2) — all VPS-side.**
- **`/products/<handle>.js`** — the money endpoint: `price`/`compare_at_price` (in **CENTS**),
  top-level `available`, `featured_image` (protocol-relative `//cdn.shopify.com/...` -> prefix
  `https:`), and `variants[]` each with `option1`=size + a real **`available`** boolean ->
  **per-size stock directly**. (NOTE: the `.js` `price_currency` field comes back `null`; the store
  is Canadian and the JSON-LD offers say **CAD** — treat `.js` prices as CAD.)
- **Composition is NOT in the `.js`.** It's in `.json` -> `product.body_html` as free prose, e.g.
  `100% GOTS certified organic 200gsm cotton, knitted locally` or `80% cotton, 20% Polyester`.
  Because the phrasing is loose (numbers like "200gsm", words like "GOTS" between the `%` and the
  fibre), do NOT try one tight regex — scan each `NN%` and grab the first fibre keyword within
  ~45 chars after it (that's what `provinceofcanada_extract.py:parse_composition` does).
- **JSON-LD `ProductGroup`** is on the PDP HTML too (3rd ld+json block; 1st=Organization,
  2nd=BreadcrumbList) with `hasVariant[].offers` (`price`, `priceCurrency: CAD`, `availability`) —
  a good cross-check / the only place currency is explicitly CAD, but the `.js` + `.json` pair is
  simpler and gives everything.

```bash
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
# price/stock/image/variants (cents), then composition:
curl -s -A "$UA" "https://provinceofcanada.com/products/<handle>.js"   -o p.js
curl -s -A "$UA" "https://provinceofcanada.com/products/<handle>.json" -o p.json  # body_html has fibre %
# list handles for a section: /collections/<c>/products.json?limit=250  or /products.json?limit=250
```

**Tested extractor:** `scripts/provinceofcanada_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-30 on four live products — Monday Tee (`100% Cotton`, $46, in stock), a Flag
Fleece Hoodie (`80% Cotton, 20% Polyester`, natural_pct 80, $138), a CFL tee (`100% Cotton`, $70,
only S in stock), a CFL hoodie (`80/20`, $160) — prices, per-size stock, and composition all
matched the live pages. Output per URL: `{handle, url, title, price, compare_at_price, on_sale,
currency, available, composition, natural_pct, image, sizes:[{size,available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-30)
| What | Where |
|---|---|
| Price / compare-at / per-size stock | `/products/<handle>.js` (prices in cents; `variants[].available`, `option1`=size) |
| Composition (fibre %) | `/products/<handle>.json` -> `product.body_html` prose (`NN% <fibre>`) |
| Currency (CAD) | PDP JSON-LD `ProductGroup.hasVariant[].offers.priceCurrency` (`.js` currency is null) |
| Image | `.js` `featured_image` (protocol-relative -> prefix `https:`) |
| Product URL | `https://provinceofcanada.com/products/<handle>` |

**Failure modes**
- `.js` `price_currency` / variant `price_currency` are **`null`** — don't infer USD from the empty
  field; it's CAD (Canadian store; JSON-LD confirms). Hard-code CAD.
- **Fibre content is loose prose, not a spec field.** A single `(\d+)%\s*(fibre)` regex misses
  `100% GOTS certified organic 200gsm cotton` (the digits/words between `%` and `cotton` break the
  match) and, worse, a naive `%` operator in the pattern string collides with Python string
  formatting. Scan each `NN%` and look ahead ~45 chars for the fibre keyword instead.
- The `.js` `body_html` key is sometimes ABSENT (seen on the CFL collab hoodie) — use `.json`'s
  `product.body_html`, which is always present, for composition.
- Duplicate/`-copy` handles exist for the same product across collections (e.g.
  `...-hoodie-copy-copy`) — dedup by title/image if listing a collection.
- Fleece / hoodies are 80/20 cotton-poly (pass 70%); check the `%` — a few blends dip lower.

## tentree (CA) — Shopify `.js` (price/stock) + PDP `fabric-composition="…"` attribute. No bot wall.

Canada, sustainable-apparel DTC (men/women/kids + accessories). **Strong natural-fibre source**
— organic cotton, hemp, and TENCEL/lyocell lines — but its "TreeBlend" tri-blend tees are ~45%
recycled polyester, so the fibre gate genuinely matters here. Canadian delivery, prices in CAD.
Domain **`tentree.ca`** (`www.` prefix). It's a Shopify store with **NO bot wall from the VPS** —
plain `urllib`/`curl` work (no exit node, no Mac delegation). Verified 2026-08-30.

**Which rung worked: Shopify JSON (rung 2) + one small PDP-HTML fetch — all VPS-side.**
- **`/products/<handle>.js`** is the money endpoint: `price`/`compare_at_price` (in **CENTS**),
  top-level `available`, `featured_image` (protocol-relative `//cdn.shopify.com/...`), and a
  `variants[]` grid with `option1`=Color / `option2`=Size, each with `price`, `compare_at_price`,
  a real **`available`** boolean (per-size stock), and `sku`. Confirmed it discriminates: the
  100% organic-cotton relaxed tee returned all sizes `available:false` (genuinely OOS) while the
  Juniper tee returned all sizes in stock.
- **Composition is NOT reliable in the JSON.** The `.js`/`.json` `description`/`body_html` only
  *sometimes* carries the fibre % (the TreeBlend Juniper spells "45% Recycled Polyester, 30%
  TENCEL™ Lyocell, 25% Organic Cotton" in prose; the plain organic-cotton tee just says "organic
  cotton" with no %). The **authoritative** composition is a single **`fabric-composition="…"`
  HTML attribute** on the PDP (static HTML — `curl` gets it, no accordion/JS click needed). It can
  contain HTML entities and an embedded `<a href='/pages/materials'>TreeBlend</a> :` prefix, so
  entity-unescape, strip tags, and drop the `Name :` prefix before parsing the `%`s.

```bash
# price/stock/image/variants (cents):
curl -s -A "$UA" "https://www.tentree.ca/products/<handle>.js"
# authoritative composition (static HTML attribute):
curl -s -A "$UA" -H 'Accept: text/html' "https://www.tentree.ca/products/<handle>" \
  | grep -oE 'fabric-composition="[^"]*"'   # -> fabric-composition="100% Organic Cotton"
```

**Tested extractor:** `scripts/tentree_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-30 on two live products:
- `mens-organic-cotton-relaxed-t-shirt-white` → "100% Organic Cotton", natural_pct 100,
  $50.00, all 5 sizes OOS (`any_in_stock:false`).
- `mens-juniper-tshirt-meteorite-black-heather` → "45% Recycled Polyester, 30% TENCEL™ Lyocell,
  25% Organic Cotton", natural_pct **55**, $45.00, all sizes in stock.
Output per URL: `{url, handle, title, vendor, type, price, compare_at_price, on_sale, available,
composition, natural_pct, image, colors[], sizes[], variants:[{color,size,price,compare_at,
available,sku}], any_in_stock}`. Image URLs verified to return `image/jpeg`.

**Selectors / endpoints** (verified 2026-08-30)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (cents; `variants[].available` per size) |
| Composition (fibre %) | PDP HTML attribute `fabric-composition="…"` (entity-encoded; strip tags + `Name :` prefix) |
| Image | `.js` `featured_image` (protocol-relative → prefix `https:`) |
| Product URL | `https://www.tentree.ca/products/<handle>` |

**Failure modes**
- **TENCEL/lyocell counts as NATURAL** (plant-derived) per the skill rule, but **recycled
  polyester does NOT** — so a "TreeBlend" tee at 45% recycled poly / 30% TENCEL / 25% cotton is
  natural_pct **55** (fails a 70% gate), not 100. The name ("…Cotton T-Shirt") lies about the
  blend — always read the `fabric-composition` %. Plain "Organic Cotton" tees are 100% cotton
  → clean pass.
- `.js`/`.json` `description` composition is inconsistent (present for blends, absent for solids)
  — don't rely on it; the `fabric-composition` attribute is the single source of truth.
- Prices are CAD but the Shopify feed doesn't stamp currency clearly — treat `tentree.ca` as CAD;
  `tentree.com` is the US catalog (fine for finding handles, but hand the user the `.ca` link).
- Handles are colour-specific for some products (`...-t-shirt-white`) — one handle per colourway,
  as with most Shopify stores.

## Oak + Fort (CA) — Shopify `.js` (price/stock) + static PDP "Materials & Care" accordion. No bot wall.

Canada, mid-market minimalist DTC (women's + men's + a little home). **Natural-fibre-friendly**:
real 100%-linen and 100%-cotton lines, though its "Linen Blend"/"Cotton Blend" pieces cut in rayon
— read the `%`. Domain **`oakandfort.com`** (the `.ca` domain 301s to `.com`; prices are CAD).
**No bot wall from the VPS** — plain `urllib`/`curl` work, no exit node, no Mac delegation.
Verified 2026-08-31.

**Which rung worked: Shopify JSON (rung 2) + one static PDP-HTML fetch — all VPS-side.**
It's a Shopify store, so the standard endpoints are open:
- **`/products/<handle>.js`** is the money endpoint: `price`/`price_min`/`price_max` (in **CENTS**),
  `compare_at_price` (original when on sale), top-level `available`, `vendor` ("Oak and Fort"),
  `featured_image` (protocol-relative `//cdn.shopify.com/...`), and a `variants[]` grid each with
  `option1`=colour / `option2`=size, `price`, `compare_at_price`, and a real **`available`** boolean
  → **per-size/per-colour stock directly**. (`.js` gives `available`; `.json` does NOT — use `.js`.)
- **Composition is NOT in the `.js`/`.json`** (the description is marketing prose; "Linen Blend"
  never states the split). The exact fibre `%` lives in the PDP **HTML**, in the **"Materials & Care"
  accordion**, in the *static* HTML (curl gets it, no click/JS needed): immediately after the
  `id="filter-materials-care-heading"` header, e.g. `100% Linen` or `55% Linen, 45% Rayon`, followed
  by care instructions on the same line. Anchor on that header id and take the leading `<NN>% Fibre`
  pairs before the care text.

```bash
# price/stock/image/variants (cents):
curl -s -A "$UA" "https://oakandfort.com/products/<handle>.js"
# exact composition (static HTML, Materials & Care accordion):
curl -s -A "$UA" -H 'Accept: text/html' "https://oakandfort.com/products/<handle>" \
  | grep -oiE 'filter-materials-care-heading[\s\S]{0,200}'   # -> "...Materials & Care 55% Linen, 45% Rayon | Exclusive of trims Dry clean only..."
```

**Tested extractor:** `scripts/oakandfort_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-31 on two live products:
- `linen-button-up-shirt-wt-10427-w` → "100% Linen", natural_pct 100, $29.99 (compare $84), OOS.
- `linen-blend-button-up-shirt-wt-14134-m` → "55% Linen, 45% Rayon", natural_pct **55**,
  $29.99 (compare $98), 3/5 variants in stock.
Output per URL: `{url, handle, title, vendor, type, price, compare_at_price, on_sale, available,
composition, natural_pct, image, colors[], sizes[], variants:[{color,size,price,compare_at,
available,sku}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-31)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in CENTS; `variants[].available`) |
| Composition (fibre %) | PDP HTML, right after `id="filter-materials-care-heading"` ("Materials & Care" accordion) |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`) |
| Product URL | `https://oakandfort.com/products/<handle>` |
| Handle | tail after `/products/`; ends in the style code (e.g. `-wt-14134-m`) |

**Failure modes**
- **Names lie about blends.** "Linen Blend Shirt" is 55% linen / 45% **rayon** → natural_pct **55**
  (rayon/viscose count synthetic per the skill rule), clears a 50% rule but fails 70%. Always read
  the accordion `%`, never trust the title.
- The Materials line runs straight into care text (`...45% Rayon | Exclusive of trims Dry clean
  only.`) — cut on care keywords (`machine wash`, `dry clean`, `hang to`, `exclusive of`, etc.)
  before parsing fibre pairs, or care words get mis-read as a fibre name.
- Per-colour handles: one handle per colourway on some products; the `.js` `variants[]` still spans
  all sizes for that colour. Top-level `available:false` can be true while some sibling colour is in
  stock — rely on per-variant `available`.
- `.ca` domain 301-redirects to `.com`; use `.com` (prices are CAD regardless).
- Discovery: `web_search "site:oakandfort.com <keyword>"` returns `/products/<handle>` links and
  the snippet often carries the composition.

## Peace Collective (CA) — Shopify `.js` (price/stock) + PDP-HTML metafield bullet (composition). No bot wall.

Canada (Toronto DTC); mid-market casual — heavyweight garment-dyed tees, crewnecks, hoodies, plus
licensed NFL/NBA/collegiate styles. **Natural-fibre-friendly on the essentials line** (the
"Heavyweight Garment Dyed T-Shirt" range is **100% cotton**), but the fleece/crewneck/licensed
styles are typically **60% cotton / 40% polyester** — so READ THE %: the 60/40 fleece clears a 50%
rule but fails 70%. **No bot wall from the VPS** — pure `urllib`, no exit node / no Mac delegation.
Verified 2026-08-31.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.**
- **`/products/<handle>.js`** is the money endpoint: `price`/`compare_at_price` (in **CENTS**),
  top-level `available`, and a `variants[]` grid each with `title`=size, `price`, and a real
  **`available`** boolean → per-size stock directly. `featured_image` is protocol-relative
  (`//cdn.shopify.com/...` → prefix `https:`).
- **Composition is NOT in the `.js`** (`description` is usually empty). It lives in the PDP **HTML**
  as a **`multi_line_text_field` bullet**: `• 60% Cotton, 40% Polyester<br /> • Machine wash…` (or
  `• 100% cotton`). It's in the *static* HTML — curl/urllib get it, no accordion click. The product
  `tags[]` sometimes mirror it (`"100% Cotton"`) but are NOT reliable — licensed styles carry no
  fibre tag — so the HTML bullet is authoritative; fall back to the tag only if the bullet is absent.

```bash
# price/stock/image/variants (cents) — MUST use the www. host:
curl -sL -A "$UA" "https://www.peace-collective.com/products/<handle>.js"
# composition — the fibre bullet in the static PDP HTML:
curl -sL -A "$UA" -H 'Accept: text/html' "https://www.peace-collective.com/products/<handle>" \
  | grep -oE 'multi_line_text_field">[^<]*'   # -> ...">• 60% Cotton, 40% Polyester
```

**Tested extractor:** `scripts/peacecollective_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-08-31 on two live products:
- `it-s-not-me-...-t-shirt-caramel` → "100% cotton", natural_pct 100, $59.00, 7/7 sizes in stock.
- `seattle-seahawks-...-crewneck-black` → "60% Cotton, 40% Polyester", natural_pct 60, $106.00, in stock.
Output per URL: `{url, title, price, compare_at_price, on_sale, available, composition,
natural_pct, image, sizes:[{size,price,available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-08-31)
| What | Where |
|---|---|
| Price / compare-at / stock / variants | `/products/<handle>.js` (prices in CENTS; `variants[].available`) |
| Composition (fibre %) | PDP HTML, `multi_line_text_field">• NN% Cotton, NN% Polyester` bullet |
| Composition fallback | product `tags[]` in `.js`/`.json` (e.g. `"100% Cotton"`) — unreliable, licensed styles omit it |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`) |
| Product URL | `https://www.peace-collective.com/products/<handle>` |

**Failure modes**
- **Must use the `www.` host.** The apex `peace-collective.com` 301-redirects `.js`/`.json`/PDP to
  `www.`; a urllib GET without redirect-follow returns the redirect stub (not JSON). Either hit
  `www.` directly or let urllib follow the 30x (`urlopen` does by default; curl needs `-L`).
- **Names/tags lie about blends.** A crewneck may read "vintage" with no fibre tag but be 60/40
  cotton/poly → natural_pct 60. Always resolve the actual `%` from the HTML bullet; don't assume the
  essentials-tee cotton rate applies to fleece.
- `description` in the `.js` is typically empty — do NOT rely on it for composition; go to the HTML.
- Discovery: `web_search "site:peace-collective.com <keyword>"` returns `/products/<handle>` links;
  `products.json?limit=N` lists handles + tags for a quick catalogue scan.

## Naked & Famous Denim — Shopify `.js` alone (price + stock + composition, all in one call). No bot wall.

Canada (Montreal), premium — a **top natural-fibre source for men's denim & tees**. Raw selvedge
jeans are almost always **100% cotton**; "stretch" cuts add ~1-2% elastane (still clears a 70% rule
comfortably); heavyweight tees are 100% cotton. Shopify store, `nakedandfamousdenim.com` — **NO bot
wall from the VPS** (plain `urllib`/`curl`, no exit node, no Mac). Verified 2026-09-01.

**Which rung worked: Shopify JSON (rung 2) — and a single `.js` call is enough.** Unusually for a
Shopify store, N&F embeds the full PDP `body_html` in the **`description` field of `/products/<handle>.js`**,
and the fibre composition is an `<li>` bullet inside it (e.g. `98% Cotton / 2% Elastane`,
`100% Cotton`). So `.js` gives price, per-size/per-colour stock, image, AND composition — no
separate HTML fetch, no JSON-LD parse, no accordion click. (`.json` `product.body_html` carries the
same bullet if you prefer it, but `.js` also has per-variant `available`, so `.js` is the one to use.)

```bash
# everything (price cents, per-size available, image, composition-in-description) in one GET:
curl -sL -A "$UA" -H 'Accept: application/json' \
  "https://www.nakedandfamousdenim.com/products/true-guy-11oz-stretch-selvedge.js" -o p.js
# composition lives in the description HTML as an <li> with a %:
python3 -c "import json,re;d=json.load(open('p.js'))['description'];print(re.findall(r'<li>([^<]*%[^<]*)</li>',d))"
# -> ['98% Cotton \xa0/ \xa02% Elastane']
```

**Tested extractor:** `scripts/nakedandfamous_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-09-01 on two live products:
- `true-guy-11oz-stretch-selvedge` -> "98% Cotton / 2% Elastane", natural_pct 98, $190 CAD,
  4/13 sizes in stock (27-28 OOS, 29-32 in).
- `strong-tee-heavyweight-11oz-jersey` -> "100% Cotton", natural_pct 100, $89 CAD, per-colour x size
  stock resolved correctly (e.g. White/XXL OOS, Natural/XXL in).
Output per URL: `{handle, title, url, price, currency(CAD), compare_at, on_sale, available,
composition, natural_pct, image, sizes:[{size,price,available}], any_in_stock}`.

**Selectors / endpoints** (verified 2026-09-01)
| What | Where |
|---|---|
| Price / compare-at / per-size stock / variants | `/products/<handle>.js` (prices in CENTS; `variants[].available`) |
| Composition (fibre %) | `.js` `description` field -> `<li>NN% Cotton / NN% Elastane</li>` (also in `.json` `body_html`) |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` -> prefix `https:`) |
| Product URL | `https://www.nakedandfamousdenim.com/products/<handle>` |
| Catalogue | `products.json?limit=250` -> handles, titles, `body_html`, `tags[]` |

**Failure modes**
- **`.js` has NO currency field** (`price_currency`/`currency` absent). The `.com` storefront bills
  in CAD — hard-code `CAD`. (JSON-LD `offers.priceCurrency` on the PDP HTML reads `USD`, which is
  WRONG for the CA-facing store — do NOT trust it; use the `.js` cents as CAD.)
- **Raw-denim / tee pages sometimes state the fabric WITHOUT a `%`** (e.g. body_html says only
  "16oz slubby Japanese selvedge denim"), so `composition` comes back `null` even though it's
  effectively 100% cotton. Treat `null` as "read the prose / assume 100% cotton for raw selvedge",
  not as a fibre-gate failure. The `%` bullet only appears when there's a blend (stretch = elastane).
- **`&nbsp;` (`\xa0`) litters the fibre bullet** (`98% Cotton \xa0/ \xa02% Elastane`) — normalise
  whitespace before parsing the `%`/fibre pairs (the extractor does).
- **Elastane is synthetic** but a stretch selvedge at 98% cotton is natural_pct 98 — clears any
  sane threshold. Watch only the rare heavy-stretch cuts; read the actual `%`.
- Discovery: `web_search "site:nakedandfamousdenim.com <keyword>"` returns `/products/<handle>`
  links; the US apex `nakedandfamousdenim.com` and `www.` both serve the same catalogue and CAD prices.

## Icebreaker (CA) — Shopify `.js` (price/stock) + PDP `<strong>Fabric content</strong>` block. No bot wall.

Canada (`na.icebreaker.com/en-ca`), mid/premium merino specialist — a **TOP natural-fibre source**:
the core Tech Lite / 200 / 260 lines are **100% merino wool**, and even the Cool-Lite "Sphere"
blends are 60% TENCEL Lyocell / 40% merino (both counted natural). Great for adult base layers,
tees, and (per the skill's no-kids'-shoes-but-apparel-OK stance) merino kids' layers. **No bot wall
from the VPS** — plain `curl`/`urllib` work; no exit node, no Mac delegation. Verified 2026-09-01.

**Which rung worked: Shopify JSON (rung 2) + a small PDP-HTML fetch — all VPS-side.** It's a Shopify
store with a **REQUIRED `/en-ca/` locale prefix**. The prefix is what makes prices come back CAD and
what stops the endpoints 302-redirecting:
- **`/en-ca/products/<handle>.js`** is the money endpoint: `price`/`compare_at_price` (in **CENTS**),
  top-level `available`, and `variants[]` each with `option1`=Color / `option2`=Size and a real
  **`available`** boolean → **per-size stock directly**. `featured_image` is protocol-relative.
- **Composition is NOT reliable in the `.js`/`body_html`** — the prose only says e.g. "100% merino"
  for pure-merino items and **OMITS the blend entirely** for Cool-Lite (body_html has no `%` at all).
  The authoritative fibre content lives in the PDP **HTML** in a structured block:
  **`<strong>Fabric content</strong><p>60% TENCEL™ Lyocell, 40% merino wool, exclusive of decoration</p>`**.
  It's in the *static* HTML (curl gets it — no click/accordion needed). Strip the trailing
  "exclusive of decoration".
- **`/en-ca/collections/<handle>/products.json?limit=N`** lists handles + `body_html` for discovery.

```bash
# price/stock/image/variants (cents), CAD via /en-ca/:
curl -s -A "$UA" "https://na.icebreaker.com/en-ca/products/<handle>.js"
# authoritative composition (static HTML):
curl -s -A "$UA" -H 'Accept: text/html' "https://na.icebreaker.com/en-ca/products/<handle>" \
  | grep -oiE '<strong>\s*Fabric content\s*</strong>\s*<p>[^<]*</p>'
  # -> <strong>Fabric content</strong><p>100% merino wool, exclusive of decoration</p>
```

**Tested extractor:** `scripts/icebreaker_extract.py` (pure `urllib`, runs on the VPS).
Verified 2026-09-01 on two live products:
- `merino-150-tech-lite-short-sleeve-t-shirt-ib0a56wl001` → "100% merino wool", natural_pct 100,
  $105 CAD, 5/7 sizes in stock (XS + XXXL OOS).
- `merino-blend-125-cool-lite-sphere-short-sleeve-t-shirt-ib0a56zm001` → "60% TENCEL™ Lyocell,
  40% merino wool", natural_pct 100, $95 CAD, all 5 sizes in stock.
Image URL confirmed `image/jpeg`; visible PDP price ($105.00) matched. Output per URL:
`{url, handle, title, type, price, compare_at_price, on_sale, currency(CAD), available,
composition, natural_pct, image, colors[], sizes[], variants:[{color,size,price,available}],
any_in_stock}`.

**Selectors / endpoints** (verified 2026-09-01)
| What | Where |
|---|---|
| Price / compare-at / per-size stock / variants | `/en-ca/products/<handle>.js` (prices in CENTS; `variants[].available`) |
| Composition (fibre %) | PDP HTML, `<strong>Fabric content</strong><p>…%…</p>` (static; NOT in `.js`/body_html) |
| Image | `.js` `featured_image` (protocol-relative `//cdn.shopify.com/...` → prefix `https:`) |
| Product URL | `https://na.icebreaker.com/en-ca/products/<handle>` |
| Catalogue | `/en-ca/collections/<handle>/products.json?limit=250` → handles, `body_html`, tags |

**Failure modes**
- **The `/en-ca/` prefix is mandatory.** Without it, `/products/<handle>.js` **302-redirects** and
  the storefront defaults to USD. Always keep `/en-ca/` on every URL (`.js`, PDP, collections).
- **CURRENCY TRAP:** the PDP JSON-LD `offers.priceCurrency` is a stale template default of **"USD"** —
  IGNORE it. The `.js` price on the `/en-ca/` path is already CAD (Tech Lite tee = C$105, matches the
  live page). Hard-code `CAD`. (Same trap as Naked & Famous / Tilley.)
- **Blend composition hides from the JSON.** `body_html`/`.js` `description` shows the `%` only for
  pure-merino items; for the Cool-Lite blends it says nothing about fibre. MUST read the PDP
  `<strong>Fabric content</strong>` block — do NOT gate on the `.js` description alone.
- Cool-Lite "Sphere"/"Cool-Lite" tees are TENCEL Lyocell + merino (both natural here). But watch any
  recycled-poly or Corespun (nylon core) variants that appear in outerwear/socks — read the actual `%`.
- Discovery: `web_search "site:na.icebreaker.com/en-ca <keyword>"` returns `/en-ca/products/<handle>`
  links directly (handles end in the style id, e.g. `-ib0a56wl001`).
