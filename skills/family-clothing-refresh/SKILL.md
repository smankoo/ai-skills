---
name: family-clothing-refresh
description: >
  Plan and buy a seasonal clothing refresh for a whole family — build a per-person checklist,
  derive and verify children's sizes from measurements, browse real retailer sites to pick
  specific in-stock pieces, write a markdown cart per person, then send formatted HTML
  "cross-store shopping cart" emails. Use when the user asks for help buying clothes for the
  family or for a child (back-to-school, starting JK/kindergarten, starting daycare, fall/winter/
  summer wardrobe, growth spurt, "the kids need clothes", "we need clothes for fall"). Also use
  for a single person's seasonal capsule wardrobe. Acts as a personal designer, not just a
  logistics planner.
---

# Family Clothing Refresh

Produce a **buyable** cart, not a list of suggestions. Every piece is a real product, at a
verified live price, confirmed in stock **in the size that person actually needs**.

Two rules govern everything:

1. **Children's sizes must be correct.** They're the one thing the user cannot fix by clicking
   through. Adults pick their own size at checkout, so an adult "size" is a non-goal.
2. **Think like a personal designer.** A correct-but-ugly list is a failure. Pieces should be
   attractive, cross-match into outfits, and cohere as a palette.

## Run it end to end

The user typically hands over the task and walks away ("don't wait for me, make educated
guesses"). Take that literally: make reasonable assumptions, note them in the output, and
finish. Don't stall on ambiguity you can resolve yourself.

Phases: **profile → checklist → browse & verify → cart files → emails.**

---

## 1. Profile the family

Gather, per person: age, current measurements (height/weight for kids), what they do all day
(school, daycare, hybrid office, at home), the local climate for that season, foot notes,
and any medical/orthopedic constraints.

If Pebbleway is available, that's the source of truth — it holds people, children, measurements,
clothing sizes, and health records:

```
mcp__pebbleway__query_graph   # find the person / child nodes and their properties
```

**Distrust a stored size; trust a stored measurement.** Sizes go stale as kids grow, and
they're often entered wrong. In the 2026 run, a child's `shoe_size` was recorded as `4` —
US 4C is an ~18-month-old's shoe, and he was four years old. Recompute from measurements and
`patch_graph` the record when you find an error.

Also mine: school/daycare websites for their actual requirements (indoor shoes, spare sets,
outdoor-in-all-weather policies, label-everything rules), and the user's own notes.

**Ask about dated events in the season, not just daily activities.** Graduations, weddings,
picture day, Diwali, family photos and religious occasions each need a specific outfit and come
with a hard deadline that ordinary wardrobe items don't have. Check the calendar
(`mcp__pebbleway__get_upcoming_events`) and the school newsletter. The 2026 run missed a
child's graduation two weeks out — his only dressed-up options were an oxford and a polo, both
under-dressed for a ceremony. Surface these early: they're the items where shipping time can
actually make you miss the date.

Never put PII from Pebbleway (SINs, health-card, passport numbers, medications) into a
shopping list or email.

## 2. Derive children's sizes from measurements — show the arithmetic

Pull the retailer's own size chart and place the child in a band. Write the reasoning into the
output so the user can check it:

> Measured 79.5 cm on 15 Jul. Gap's 12-18M = 74–79 cm, 18-24M = 79–84 cm. He is already *past*
> the top of 12-18M, and will be ~82–84 cm by October — mid-band in 18-24M.

Bias **up** when a child is near the top of a band: clothes bought in September are worn
through June. Say so explicitly ("4T would be tight by Christmas").

**Never order shoes.** Foot length can't be inferred from height, a wrong size affects how a
young child walks, and lasts vary by brand. Instead emit a measure-first instruction plus a
cm→size table for the expected range:

| Foot length | Size |
|---|---|
| 16.9 cm | US 10.5C |
| 17.3 cm | US 11C |
| 17.6 cm | US 11.5C |

Then say what to buy once measured (e.g. indoor classroom shoes, everyday sneakers, rain
boots — all velcro, no laces, for a child who dresses himself).

## 3. Write the checklist first

Before shopping, produce `00-CHECKLIST.md`: who needs what and **how many**, with the
reasoning. This is what keeps the cart honest later.

Derive counts from laundry cadence, not vibes. Roughly, per child per season:
7–8 bottoms, 8–10 tops, 3–4 layers, 2 outerwear, 2 sleep sets, plus socks/underwear
multipacks. Daycare needs *more* bottoms (highest churn, several changes a day) and two full
spare sets for the cubby.

For each person, name the **governing constraint** in one line — it does more to shape the
list than any style preference:

- Child dressing himself at school → pull-on elastic waists only; no button flies, belts, or
  back zippers. Even the jeans must be pull-on.
- Daycare → staff change him fast, several times a day; soft, stretchy, industrial-wash, nothing
  precious. **No neck drawstrings** (strangulation hazard, banned at licensed centres).
- Hybrid office adult → the real gap is the *transitional layer* for ~15 °C: too warm for a coat,
  too cool for shirtsleeves. Overshirts.
- Parent doing school runs then dinner → "elevated everyday": washable, no ironing, but genuinely
  put-together. Test: *wearable to a park and then straight to dinner without changing.*

## 4. Quantity: `×N` only where duplication is genuinely right

Do **not** write "get 7 of these." Do **not** pad to 7 with 7 different novelties either.
Split deliberately:

- **`×N` of one piece** when it's the daily-reach item and colour is the only variable —
  "Fleece joggers ×2, buy two colours."
- **Distinct pieces** when variety is the point — four shirts in four *fabrics* (flannel,
  corduroy, oxford, brushed plaid), not four flannels.
- **Multipacks** where they're honestly better: plain long-sleeve solids for layering, socks,
  underwear. Justify it (a 6-pack at $37.49 vs ~$45 bought singly) so it doesn't read as lazy.

## 5. Design it, don't just fill slots

- Pick a **palette** and state it: neutral base, two warm counterpoints, one light knit so it
  doesn't go funereal.
- Make it **cross-match**: every top should work with every bottom. Say that it's deliberate.
- Prove it with **"Three outfits this makes"** — three named scenarios at real temperatures.
  This is the single most convincing part of the output.
- Give a **priority subset** for anyone who blanches at the total: the 3–4 pieces that cover
  most of the season, with their sum. Note which big-ticket item can wait for a sale.
- Separate the *workhorse* from the *nice thing* explicitly, and let the workhorses be cheap.

## 6. Store routing

Default mapping (adjust to the user's stated habits — ask nothing, just read their message):

| Who | Where | Why |
|---|---|---|
| Kids, nicer pieces | Gap | Picture day, gurdwara, family occasions |
| Kids, play clothes | Old Navy | Resilient, low-visibility; a ruined knee costs $12 not $40 |
| Adults | Simons (Le 31 / Twik / Contemporaine / Icône) | House brands, good value |
| Anyone, fallback | Amazon.ca | Gap-fillers |

Watch for sales — Old Navy running ~50% off is why two children's wardrobes can come in under
$850. Say when pricing won't hold.

## 7. Browse and verify — the part that actually takes the time

Use the browser MCP. See `references/retailer-recipes.md` for the working extraction
snippets, category IDs, and every failure mode hit so far. The essentials:

- **Simons**: parse the `application/ld+json` block on each product page for `name`, `brand`,
  `offers.price`, `offers.availability`. Category URLs bounce to the homepage under bot
  protection — use a **same-origin `fetch()` from an already-loaded tab** instead.
- **Gap / Old Navy**: a size is out of stock when its `<label for="pdp_buybox_dimension_…">`
  carries `fds_selector__label--unavailable`. Check the **child's exact size**, not just that
  the product exists. In the 2026 run this caught **nine** pieces that looked fine on the
  category grid but were unbuyable in the size needed.
- **One tab per origin.** Cross-origin `fetch()` fails.
- Page-scoped helpers (`window.__V`) die on navigation — redefine after every navigate.
- A suspiciously cheap item (e.g. everything at `$9.99`) is usually **sold-out clearance**, not
  a bargain. Confirm `InStock` before believing a price.

If you delegate browsing to subagents, **do not let several of them share one browser** — they
deadlock in sleep-retry loops. Either drive the browser yourself or give agents disjoint,
short-lived jobs. If they do stall, their JSONL output files under the session dir can be
parsed to salvage verified products rather than re-running everything.

## 8. Write one markdown file per person

`00-CHECKLIST.md`, then `01-<name>.md`, `02-<name>.md`, …

Each file: brief + governing constraint, palette, sections by category with a `Qty | Piece |
Store | Price | Link` table, the reasoning under each section, "three outfits", the total,
the priority subset, and any not-ordered warnings (shoes) or availability caveats.

State the capture date and that stock was verified: *"Every item below was checked in stock in
18-24M on 4 Aug."*

## 9. Build and send the emails

Prices live in a JSON cart per person; the builder computes every subtotal and total. This is
deliberate — in the first run, three of four hand-written totals were arithmetically wrong.
**Never hand-write a total.**

```bash
# 1. Write one cart JSON per person (schema: references/cart-schema.md)
# 2. Build HTML from the shared shell — all four look identical by construction
python3 scripts/build_emails.py carts/*.json --out-dir out/

# 3. Send each
python3 scripts/send_email.py \
  --to sumeet@mankoo.ca --to priya.ark@gmail.com \
  --subject "Fall 2026 shopping cart — Tegh (JK, size 5T)" \
  --html out/email-01-tegh.html
```

`build_emails.py` prints each computed total and cross-checks it against an optional
`expect_total` in the JSON, so a mismatch fails loudly instead of shipping.

**If the email presents alternatives rather than one list** (e.g. three outfit options for one
occasion, pick one), the builder still sums *everything* — so the grand total is arithmetic, not a
price. Don't fight this: set `expect_total` to that real sum so the guard rail keeps working, lean
on the per-section subtotals as the numbers that matter, and say so explicitly in both the opening
note and the footnote. Also give an actual recommendation; three options with no opinion pushes the
decision back onto the user, which is the opposite of the job.

`send_email.py` reads iCloud credentials at runtime from `~/.config/owlpost/accounts.toml`.
**Never hardcode or print the password.** It APPENDs to the Sent folder manually because
iCloud SMTP doesn't. If owlpost's MCP is connected, `mcp__owlpost__send_email` works too.

Email conventions, all enforced by the shared shell in `assets/email-template.html`:

- One email per person, **identical formatting** across all of them.
- Hyperlink every item name to its product page; show the price beside it.
- `×N` quantity badges where quantity > 1.
- Per-section subtotals and a single prominent total.
- **A thumbnail on every item** (`image` in the cart JSON). The user asked for these explicitly —
  they make the email browsable without opening 20 tabs. Collect image URLs while you're already
  on the rendered category grid; going back for them afterwards means re-navigating every page.
  See the image section of `references/cart-schema.md`, including the two pre-send checks
  (every URL returns `image/*`; the images are distinct from one another).
- Size banner at the top for children, with the derivation in one line.
- Callout blocks: info (green) for design notes, warn (amber) for measure-feet-first and
  availability caveats.
- Footer noting prices were captured on a date and will drift.

Before sending, verify: no `{{PLACEHOLDER}}` survives, link count is sane, and — per the
user's global instruction — **no Claude/AI attribution anywhere** in the emails or in any
commit or public artifact.

## Report back

Give a per-person table of item counts and totals, the grand total, how sizes were derived and
verified, and the 2–3 things needing the user's attention (shoes not ordered and why, sale
timing, sizes that sell out fast). Be concrete about what was *not* bought and why — winter
parkas in August, footwear needing in-person fitting.

## Known-good reference

`references/example-run-2026-fall.md` — the original run: 4 people, 73 items, $3,623.04,
with the sizing derivations and each error caught along the way.
