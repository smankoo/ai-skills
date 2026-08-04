# Retailer recipes

Working extraction snippets and every failure mode hit so far. Verified 2026-08-04.

All of these run through the browser MCP:
`mcp__browser__browser_execute_js`, `browser_navigate`, `browser_new_tab`, `browser_list_tabs`.

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
