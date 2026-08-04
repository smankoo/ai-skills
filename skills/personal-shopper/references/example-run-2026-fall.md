# Example run — a family of four, fall 2026

The original run. Useful as a shape to imitate and a record of what went wrong. Anonymised: the
people are described by role, because this skill carries no one's personal data.

**Request:** two young children starting junior kindergarten and daycare in September, two adults
needing fall clothes. Checklist first, then real pieces from real stores, one markdown file each,
then a formatted email per person to two recipients. The kids' sizes had to be right; the adults'
didn't matter, because they'd click through and pick their own.

## Result

| Person | Situation | Store mix | Items | Total |
|---|---|---|---|---|
| Child A, 4 | Junior kindergarten, size 5T | Value chain + mid-market | 23 | $467.83 |
| Child B, ~1.5 | Daycare, size 18-24M | Value chain + mid-market | 21 | $375.36 |
| Adult A | Hybrid-office capsule | Department store | 17 | $1,853.95 |
| Adult B | Elevated-everyday capsule | Department store | 12 | $925.90 |

**Grand total $3,623.04.** Both children's full wardrobes came to $843 together, because the value
chain was running ~50% off that week — worth stating, because it means the pricing won't hold.

Deliverables: `00-CHECKLIST.md`, one markdown file per person, plus four HTML emails off one shared
shell.

## Sizing — the part that mattered

- **Child B → 18-24M.** Measured 79.5 cm / 10.2 kg three weeks earlier. The retailer's 12-18M band
  is 74–79 cm and 18-24M is 79–84 cm, so the child was already *at the ceiling* of the smaller band
  and would be ~82–84 cm by October. Buying 12-18M would have bought clothes outgrown in weeks.
- **Child A → 5 YRS/5T.** ~43 in, above the 42 in top of the 4 YRS band. 4T would have been tight
  by Christmas.
- Then **every** kids' item was individually confirmed in stock in that exact size. This caught
  **nine** pieces that appeared on the category grid but were unbuyable in the size needed.

## Governing constraints, per person

These shaped the lists more than any style preference — one line each is enough:

- **A preschooler who dresses himself:** pull-on elastic waists only, no button flies, belts, or
  back zippers. Even the jeans were pull-on. Water-resistant outerwear mattered because the school
  board's kindergarten page says the class goes outside "in all kinds of weather."
- **A toddler in daycare:** staff change him fast, several times a day — soft, stretchy, industrial
  wash, nothing precious, **no neck drawstrings**. Bottoms got the highest count.
- **A hybrid-office adult:** the real wardrobe gap was the transitional ~15 °C layer, so three
  overshirts became the spine of the capsule.
- **A parent doing school runs then dinner:** "elevated everyday" — park then dinner without
  changing.

Note the shape of these: each is a *constraint on the mechanics of getting dressed*, not a taste
preference. That's what makes them useful.

## Errors caught (each one is now a rule in the skill)

| Error | Fix |
|---|---|
| Three of four hand-written totals were arithmetically wrong | Compute every total in code. This is why `build_emails.py` exists and takes numeric prices |
| The records held a preschooler's shoe size as "4" — an 18-month-old's size | Recomputed, patched the record, and never ordered shoes |
| Four picks were sold-out clearance showing $9.99 | Require `InStock`; treat a suspiciously low price as a gone-item signal |
| A men's linen henley was reported at $89, actually $39.95 | Read the price from JSON-LD, not from a subagent's prose |
| One product id was OOS in *both* target sizes despite showing on the grid | Per-size check; substituted a sibling colourway |
| Department-store category pages bounced to the homepage (bot protection) | Same-origin `fetch()` + JSON-LD from a loaded tab |
| Cross-origin `fetch()` to a second retailer from the first one's tab failed | One tab per origin |
| Several guessed category IDs returned empty grids or the wrong department | Scrape nav links from a known-good page |
| Four subagents deadlocked fighting over one browser | Don't share a browser; parse their JSONL to salvage work |
| A page-scoped `window.__G` helper was lost after each navigation | Redefine the helper after every navigate |

## Follow-on discovered later

One child had a **graduation about two weeks out** that the original checklist missed — the only
dressed-up options on his list were an oxford shirt and a polo, which is under-dressed for a
ceremony, and the date left little shipping margin. Handled as a separate small cart and its own
email rather than by editing the shipped one.

**Lesson:** ask about *dated events* in the season, not just daily activities. Graduations, weddings,
picture day, Diwali, family photos, and religious occasions all need a specific outfit, and they have
hard deadlines that ordinary wardrobe items don't.

### How the graduation cart came out

$52.89 / $55.48 / $58.00 across three **alternatives**, not a combined list. Findings worth keeping:

- **Neither mid-market chain sold a toddler blazer**, in any size. One's dress trousers started at
  kids' size 6 — too big for a 5T child. The department store had no kids' department at all. For a
  formal toddler outfit, a large marketplace was effectively the only source.
- **Lead time beats price when the date can't move.** The cheaper blazer ($47.49, next-day) topped
  out a size below what the child actually needed. Paid $5 more for the size that fits, accepting a
  delivery date three days before the ceremony rather than a week of margin on the wrong size.
- **Presenting alternatives breaks the total.** The builder sums every section, so a three-option
  email's grand total is meaningless arithmetic. Set `expect_total` to that real sum so the guard
  rail still works, then say plainly in the intro *and* the footnote that the total is the sum of all
  three and the per-option subtotals are the numbers that matter. Don't try to suppress the total.
- **Reuse is a selling point.** Two of one option's three pieces were already on the fall list,
  making the recommended option $19.99 of new spend. Worth stating explicitly — and worth
  double-checking that a row copied from another cart keeps its *original* store, product id, and
  price. One row was briefly mislabelled as the pricier retailer's item at that retailer's price
  while still carrying the cheaper one's image and pid.
- Occasion carts should carry the adjacent non-clothing dependencies: shoes still needing an
  in-person fitting, and a haircut that wanted pulling forward ahead of the photos.
