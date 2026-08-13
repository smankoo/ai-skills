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

<!-- APPEND NEW ROWS ABOVE THIS LINE. Keep newest investigations discoverable. -->

## Candidate queue (not yet tried — good picks for future runs)

Canadian-delivering, mix of natural-fibre-friendly and kid/adult coverage. Pick from here when
choosing the next retailer, or choose another that fits Sumeet's household better:

- **Roots** (roots.com) — Canadian, heavy cotton/fleece; kids + adults; natural-fibre-friendly.
- **Frank And Oak** (frankandoak.com) — Canadian, cotton/wool/linen focus, sustainability angle.
- **Marks / Mark's** (marks.com) — workwear, cotton basics, Canadian Tire platform.
- **Tilley** (tilley.com) — natural-fibre travel/outdoor, Canadian.
- **MEC** (mec.ca) — outdoor co-op; merino/cotton available; Canadian.
- **Kotn** (kotn.com) — Canadian, Egyptian-cotton essentials; very natural-fibre-friendly.
- **Hudson's Bay** (thebay.com) — department store, house + designer brands; kids + adults.
- **Peavey Mart / Carhartt CA** — durable cotton/duck workwear.
- **Zara CA** (zara.com/ca) — fast fashion; check bot wall class.
- **Mountain Warehouse CA**, **Decathlon CA** — value outdoor.
- **Well.ca**, **Indigo** (chapters.indigo.ca) — non-clothing gift directions (books, home).
- **Amazon.ca** — already usable per SKILL.md §8; a fallback, not a recon target.
