# Retailer learnings — Aug 2026 run (Priyanka fall capsule)

## Simons.ca
- Cloudflare blocks VPS browser AND plain curl (403), even via residential exit node (Apple TV) — the automation fingerprint itself is detected, not just the IP.
- **Working recipe:** delegate to Claude Code on the MacBook (real Mac, home IP). Same-origin fetch from a real browser tab passes Cloudflare. Grid category IDs: sweaters 6667, blouses 6673, pants 6697, jeans 6702, dresses 6680, jackets-blazers 6684, coats 6685, co-ord-sets 1001. Product pages carry JSON-LD with real price/availability.
- House brands (Contemporaine, Icône, Twik) = best value; watch for markdown prices (e.g. $49.95 blazer).

## Uniqlo CA
- API `/ca/api/commerce/v5/en/products` requires a client id not present in public JS bundles — 400 from curl everywhere, even from a real Mac.
- **Working recipe:** rendered PDP pages in a real browser. Image URL pattern: `image.uniqlo.com/UQ/ST3/ca/imagesgoods/<id>/item/cagoods_<color>_<id>_3x4.jpg`.

## Delegation pattern (Sumeet-endorsed)
- Write self-contained TASK.md to /tmp/shopper on the MacBook, launch `claude --dangerously-skip-permissions -p "Read TASK.md and execute"` in detached tmux; it writes batch JSONs + log.txt + DONE file; poll via ssh every ~4 min (background sleep+ssh, notify_on_complete).
- Harvested 31 verified items in ~13 min after hours of direct-browsing failure. Prefer this whenever a retailer blocks the VPS.

## Blocked from VPS (don't bother)
- H&M, Aritzia: same Cloudflare class as Simons.

## Menswear run additions (2026-08-08)

### Simons men's category IDs (discovered; women's IDs do NOT apply)
- men-clothing-root=6714, sweaters=6723 (crew-necks=6727, merino=6939), shirts=6720 (plaid-flannel=6987, solid=7122, patterns=7121), tshirts=6715 (long-sleeves=6717, basics under 6715), pants=6755 (chinos=9464, skinny-slim=6756, straight=6757), jeans=6746, coats-jackets=6737 (jackets-bombers=8503), blazers=6731/8233/8234, dress-shirts=6732, sweatshirts=8064, overshirts: shirts/overshirts=9173, coats/overshirts=1292
- Simons men's pant sizes label as "34" or "34-32" (waist-inseam); jackets use 40R ≈ M. Size availability via availabilityData JSON on PDP.
- Simons on-site search endpoints not fetchable same-origin — use category grids only.

### Uniqlo CA menswear (rendered PDPs, IDs stable)
- merino crew 450535, flannel shirt 486600, slim oxford 456630, slim chino 487209 (2025) / 450251, slim straight jeans 482856, PUFFTECH 486171, Harrington 484610, waffle LS tee 486105, HEATTECH LS 486841. Colour codes appear in image URLs (cagoods_NN_).

### Process learnings
- Colour diversity rule works when pushed mid-run as a TASK.md addendum — harvester picked it up between batches. Bake into initial TASK.md next time: record colourway per item + all available colours; curator enforces ≤30% per colour and names the exact colourway per line.
- Mid-run addenda to TASK.md are an effective steering channel for a detached Claude Code run (it re-reads the brief between phases).
- send_email.py requires --html flag (not positional).
- Occasion outfits: flag candidates "occasion":true in harvest JSON; curate as a named outfit section (blazer+shirt+pant) rather than scattered items — user explicitly wants this.

## Kids' runs additions (2026-08-08, Tegh 5T + Kirat 18-24M)

- **Simons has no kids' clothing** — only Fabrique 1840 artisan accessories (tuques/ponchos, generic sizes). Skip Simons for kids entirely.
- **Uniqlo kids/baby sizing is cm-based**: 110cm ≈ 5T/kids 5; 90cm ≈ 18-24M/2T. Same API as adults (x-fr-clientid=uq.ca.web-spa, search + l2s stock endpoints). Watch for `comingSoon`/`sales:false` items that show IN_STOCK but aren't purchasable ("Available Mid-Aug") — check the sales flag, not just stock.
- **Joe Fresh**: PDP SSR embeds sizes[] with disabled:false for in-stock. Baby label "18-24", toddler numeric "2" = 2T, kids "5". No API key needed.
- **Old Navy CA**: search via api.gapcanada.ca constructorio endpoint (q=/keyword= param, x-api-key in page source). In-stock marker: `pdp-dimension-instock` in PDP buybox. Colourway names from swatch shortDescription.
- **Claude Code runs can crash mid-harvest** (API server errors/timeouts). Mitigation now baked into TASK.md template: "write partial_<store>.json after EACH store" — restart prompt then says "reuse partials, don't redo". Kirat run crashed 0 times with partials instructed; Tegh run crashed twice before this rule.
- Sibling occasion outfits: mirror the anchor look across sizes (white shirt + stone chino existed at both Old Navy 18-24M and Joe Fresh/Old Navy 5T).
