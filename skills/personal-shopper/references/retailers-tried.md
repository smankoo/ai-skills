# Retailers tried — reconnaissance ledger

**Purpose.** A running log so the twice-daily reconnaissance job never re-investigates a retailer
it already cracked. Each run picks a retailer **not already `done` below**, works out the best way
to pull product data (API / frontend / Shopify JSON / rendered PDP), records the mechanics in
`retailer-recipes.md`, and adds a row here.

**Status legend**
- `done` — a working, tested extraction recipe exists in `retailer-recipes.md`.
- `blocked` — a hard wall with no VPS-side workaround found yet (see `retail-bot-wall-bypass` skill).
- `partial` — some data extractable, but incomplete (e.g. price but not composition/stock).
- `wip` — investigated but not yet a repeatable recipe.

**How to use each run**
1. Read this whole file first. Do NOT pick a retailer with status `done`.
2. Prefer a retailer that fits Sumeet's household (Canadian delivery; natural-fibre-friendly lines;
   kids + adults; his stated stores) — but variety across runs is the goal.
3. After investigating, append/update a row here AND push. One retailer per run is plenty.

| Retailer | Country | Method that works | Status | Recipe? | Last verified |
|---|---|---|---|---|---|
| Uniqlo CA | CA | Public JSON API (`x-fr-clientid: uq.ca.web-spa`), same-origin fetch | done | yes | 2026-08-13 |
| Herschel | Global | Shopify storefront JSON (`/products/<handle>.json`, `suggest.json`) | done | yes | 2026-08-13 |
| Simons | CA | JSON-LD via same-origin fetch (Mac; VPS Cloudflare-blocked) | done | yes | 2026-08-08 |
| Gap CA | CA | `/browse/product.do` HTML, per-size `--unavailable` label | done | yes | 2026-08-04 |
| Old Navy CA | CA | Same Gap platform; constructor.io search; `pdp-dimension-instock` | done | yes | 2026-08-08 |
| Joe Fresh | CA | PDP SSR embeds `sizes[]` with `disabled:false` | done | yes | 2026-08-08 |
| H&M CA | CA | Cloudflare (same class as Simons) — Mac delegation only | blocked | note | 2026-08-08 |
| Aritzia | CA | Cloudflare (same class as Simons) — Mac delegation only | blocked | note | 2026-08-08 |
| Costco.ca | CA | Press-and-Hold interactive challenge; deep product URLs sometimes clear | blocked | note | 2026-08-12 |
| Wayfair.ca | CA | Press-and-Hold; CDP windowed Chrome on Mac works for product pages | partial | note | 2026-08-12 |
| Pottery Barn Kids CA | CA | Loads clean via CDP windowed Chrome on Mac | done | note | 2026-08-12 |
| The Brick | CA | Press-and-Hold on grids; CDP windowed Chrome + deep links works | partial | note | 2026-08-12 |
| The Children's Place | CA | Rendered-DOM via web_extract + `childrensplace_extract.py` (no JSON-LD/API) | done | yes | 2026-08-15 |
| Carter's / OshKosh CA | CA | JSON-LD `ProductGroup` (per-size price+stock) via CDP Chrome on Mac; `carters_extract.py`. VPS fully walled (CF+PerimeterX) | done | yes | 2026-08-15 |

<!-- APPEND NEW ROWS ABOVE THIS LINE. Keep newest investigations discoverable. -->

## Candidate queue (not yet tried — good picks for future runs)

### ⭐ CONFIRMED FROM SUMEET'S YNAB PURCHASE HISTORY — prioritize these first

These are retailers Sumeet has **actually purchased from** (verified against his YNAB payee list,
2026-08-13). A recon run should prefer these over speculative picks — a working recipe here has
immediate real-world value. Grouped by role; ones already cracked are marked.

**Apparel & footwear**
- Uniqlo Canada — ✅ `done` (see recipe). His confirmed kids' store.
- Old Navy CA — ✅ `done`. His confirmed kids' store.
- Gap CA — ✅ `done`.
- La Maison Simons — ✅ `done` (Mac delegation).
- Aritzia — `blocked` (Cloudflare); worth a fresh Mac-CDP attempt.
- **Zara CA** (zara.com/ca) — bought at Square One; check bot-wall class.
- **The Children's Place** (childrensplace.com/ca) — ✅ `done` (see recipe). Kids' workhorse clothes.
- **Carter's / OshKosh CA** (cartersoshkosh.ca) — ✅ `done` (see recipe). Baby/toddler, mostly 100% cotton. VPS-walled → Mac CDP.
- **Reitmans** (reitmans.com) — women's (Priyanka).
- **La Vie En Rose** (lavieenrose.com) — lingerie/loungewear.
- **Tommy Hilfiger CA** — natural-fibre-friendly (cotton oxfords/chinos).
- **Michael Kors CA** — accessories/gifts.
- **Aldo** (aldoshoes.com) — footwear (note skill's "never order kids' shoes" rule; adults OK).
- **Crocs CA** — footwear.
- **ASICS Canada** — athletic footwear.
- **Sport Chek** (sportchek.ca) — athletic apparel/gear; his fitness angle (Strava/Fitbod).
- **Winners** (winners.ca) — off-price; likely no online catalog, verify.

**General merchandise / marketplace / home**
- Amazon.ca — usable per SKILL.md §8 (his single most-used retailer by far); a fallback, not recon.
- **Walmart CA** (walmart.ca) — used via Instacart + direct; general merch + kids.
- **Costco CA** — `blocked` (press-and-hold); membership warehouse, his CIBC Costco card.
- **Canadian Tire** (canadiantire.ca) — Triangle Rewards member; home/auto/seasonal.
- **IKEA CA** (ikea.ca) — furniture/home; frequent.
- **Indigo / Chapters** (chapters.indigo.ca) — books & gifts.
- **Staples CA** (staples.ca) — office/electronics.
- **Michaels** (michaels.com) — crafts/gifts.
- **Party City CA** (partycity.ca) — party/kids events.
- **Toys R Us CA** (toysrus.ca) — kids' gifts.
- **RONA** (rona.ca) — home improvement.

**Beauty / personal care**
- **Deciem / The Ordinary** (deciem.com) — skincare; Shopify-ish, likely easy.
- **The Body Shop CA** — natural beauty.
- **Bath & Body Works CA** — gifts.

**Specialty / gifts**
- **Brilliant Earth** (brilliantearth.com) — fine jewelry (a real past purchase; gift direction).
- **EyeBuyDirect** (eyebuydirect.com) — prescription eyewear.
- **Etsy** — handmade/gifts (has a public API + JSON-LD).

### Other good picks (not confirmed in YNAB, but fit the household)

- **Roots** (roots.com) — Canadian, heavy cotton/fleece; kids + adults; natural-fibre-friendly.
- **Frank And Oak** (frankandoak.com) — Canadian, cotton/wool/linen focus, sustainability angle.
- **Mark's** (marks.com) — workwear, cotton basics, Canadian Tire platform.
- **Tilley** (tilley.com) — natural-fibre travel/outdoor, Canadian.
- **MEC** (mec.ca) — outdoor co-op; merino/cotton; Canadian.
- **Kotn** (kotn.com) — Canadian, Egyptian-cotton essentials; very natural-fibre-friendly.
- **Hudson's Bay** (thebay.com) — department store, house + designer brands; kids + adults.
- **Mountain Warehouse CA**, **Decathlon CA** — value outdoor.
