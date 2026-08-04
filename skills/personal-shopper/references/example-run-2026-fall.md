# Example run — Fall 2026, family of four

The original run, 2026-08-04. Useful as a shape to imitate and a record of what went wrong.

**Request:** two kids starting JK and daycare in September, two adults needing fall clothes.
Checklist first, then real pieces from real stores, one markdown file each, then a formatted
email per person to two recipients. Kids' sizes had to be right; adults' didn't matter because
they'd click through and pick their own.

## Result

| Person | Situation | Store mix | Items | Total |
|---|---|---|---|---|
| Tegh, 4 | Junior Kindergarten, size 5T | Old Navy + Gap | 23 | $467.83 |
| Kirat, ~1.5 | Daycare, size 18-24M | Old Navy + Gap | 21 | $375.36 |
| Sumeet | Hybrid office capsule | Simons | 17 | $1,853.95 |
| Priyanka | Elevated everyday capsule | Simons | 12 | $925.90 |

**Grand total $3,623.04.** Two children's full wardrobes came to $843 because Old Navy was
running ~50% off.

Deliverables: `00-CHECKLIST.md`, `01-tegh.md`, `02-kirat.md`, `03-sumeet.md`, `04-priyanka.md`,
plus four HTML emails off one shared shell.

## Sizing — the part that mattered

- **Kirat → 18-24M.** Measured 79.5 cm / 10.2 kg on 2026-07-15. Gap's 12-18M is 74–79 cm and
  18-24M is 79–84 cm, so he was already *at the ceiling* of the smaller band and would be
  ~82–84 cm by October. Buying 12-18M would have bought clothes outgrown in weeks.
- **Tegh → 5 YRS/5T.** ~43 in, above the 42 in top of the 4 YRS band. 4T would be tight by
  Christmas.
- Then **every** kids' item was individually confirmed in stock in that exact size. This caught
  **nine** pieces that appeared on the category grid but were unbuyable in the needed size.

## Governing constraints, per person

These shaped the lists more than any style preference:

- **Tegh:** has to dress himself — pull-on elastic waists only, no button flies, belts, or back
  zippers. Even the jeans were pull-on. Water-resistant outerwear mattered because the school
  board's kindergarten page says the class goes outside "in all kinds of weather."
- **Kirat:** daycare staff change him fast, several times a day — soft, stretchy, industrial
  wash, nothing precious, **no neck drawstrings**. Bottoms got the highest count.
- **Sumeet:** the real wardrobe gap was the transitional ~15 °C layer, so three overshirts
  became the spine of the capsule.
- **Priyanka:** "elevated everyday" — park then dinner without changing.

## Errors caught (each one is now a rule in the skill)

| Error | Fix |
|---|---|
| Three of four hand-written totals were arithmetically wrong | Compute every total in code. This is why `build_emails.py` exists and takes numeric prices |
| Pebbleway had Tegh's shoe size as "4" — an 18-month-old's size | Recomputed, `patch_graph`'d the record, and never ordered shoes |
| Four of Priyanka's picks were sold-out clearance showing $9.99 | Require `InStock`; treat a suspiciously low price as a gone-item signal |
| A men's linen henley was reported at $89, actually $39.95 | Read the price from JSON-LD, not from a subagent's prose |
| Gap pid 892689073 was OOS in *both* target sizes despite showing on the grid | Per-size check; substituted 892689013 |
| Simons category pages bounced to the homepage (bot protection) | Same-origin `fetch()` + JSON-LD from a loaded tab |
| Cross-origin `fetch()` to Gap from the Simons tab failed | One tab per origin |
| Several guessed category IDs returned empty grids or womenswear | Scrape nav links from a known-good page |
| Four subagents deadlocked fighting over one browser | Don't share a browser; parse their JSONL to salvage work |
| `window.__G` lost after each navigation | Redefine the helper after every navigate |

## Follow-on discovered later

Tegh had a **graduation on 21 Aug** that the original checklist missed — his only dressed-up
options were an oxford shirt and a polo, which is under-dressed for a ceremony, and the date
left little shipping margin. Handled as a separate small cart and its own email rather than by
editing the shipped one.

**Lesson:** ask about *dated events* in the season, not just daily activities. Graduations,
weddings, picture day, Diwali, family photos, and religious occasions all need a specific
outfit, and they have hard deadlines that ordinary wardrobe items don't.

### How the graduation cart came out

$52.89 / $55.48 / $58.00 across three **alternatives**, not a combined list. Findings worth
keeping:

- **Neither Gap nor Old Navy sells a toddler blazer**, in any size. Gap's dress trousers start at
  kids' size 6 — too big for a 5T child. Simons has no kids' department at all. For a formal
  toddler outfit in Canada, Amazon is effectively the only source.
- **Lead time beats price when the date can't move.** The cheaper blazer ($47.49, next-day) topped
  out at 4-5T on a child already mid-band in 5T. Paid $5 more for the size that actually fits,
  accepting a 18 Aug delivery against a 21 Aug deadline.
- **Presenting alternatives breaks the total.** The builder sums every section, so a
  three-option email's grand total is meaningless arithmetic. Set `expect_total` to that real sum
  so the guard rail still works, then say plainly in the intro *and* the footnote that the total
  is the sum of all three and the per-option subtotals are the numbers that matter. Don't try to
  suppress the total.
- **Reuse is a selling point.** Two of Option B's three pieces were already on the fall list,
  making the recommended option $19.99 of new spend. Worth stating explicitly — and worth
  double-checking that a row copied from the fall cart keeps its *original* store, pid, and
  price. One row was briefly mislabelled as a Gap item at a Gap price while carrying the Old Navy
  image and pid.
- Occasion carts should carry the adjacent non-clothing dependencies: shoes still needing an
  in-person fitting, and a haircut task that wanted pulling forward ahead of the photos.
