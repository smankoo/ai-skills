---
name: personal-shopper
description: >
  Act as a personal shopper: research who it's for, decide what's worth buying, browse real
  retailer sites to pick specific in-stock items at verified live prices, then send a formatted
  HTML "shopping cart" email with thumbnails. Use for seasonal clothing refreshes (back-to-school,
  starting JK/kindergarten or daycare, fall/winter/summer wardrobe, growth spurt, "the kids need
  clothes"), for occasion outfits with a hard date (graduation, wedding, picture day, Diwali), and
  for gift shopping ("we need a gift for X", birthday, milestone birthday, anniversary,
  housewarming, Christmas) — including finding several distinct gift directions and pricing each.
  Also use for a single person's capsule wardrobe. Acts as a designer and a thoughtful gift-giver,
  not a logistics planner.
---

# Personal Shopper

Produce a **buyable** cart, not a list of suggestions. Every item is a real product, at a
verified live price, confirmed in stock — **in the size that person needs**, and **in time for the
date that matters**.

Three rules govern everything:

1. **Children's sizes must be correct.** They're the one thing the user cannot fix by clicking
   through. Adults pick their own size at checkout, so an adult "size" is a non-goal.
2. **Think like a designer, or like someone who knows the recipient.** A correct-but-ugly list is
   a failure, and so is a gift that any stranger could have chosen. Clothing should cross-match
   and cohere as a palette; a gift should reflect something true about the person.
3. **Verify, then recommend.** Stock, price, size, and delivery date all get checked against the
   live page — and then you say which one you'd pick, and why.
4. **Leave the skill smarter than you found it.** Every run teaches something about how a retailer
   works. Write it down (§11) — otherwise the next run rediscovers it at full cost.

**This skill deliberately holds no personal data.** No names, sizes, addresses, budgets, email
addresses, favourite stores, or family structure are baked in anywhere. Everything specific comes
from the person's own records (Pebbleway, if connected), from the request itself, or from asking.
Any number or store below is an illustrative default, not a fact about whoever is running it —
treat every one as overridable and check it against the actual user. Keep it this way when editing:
this skill is shareable precisely because it's empty of any one household.

**Look up the user's standing shopping preferences before you shop — every run, step zero.** The
user accumulates durable rules about what they will and won't buy (fabric/material constraints,
brands to avoid, sustainability or fit requirements, email-format expectations like item
thumbnails). These live in persistent memory, not in this file, and they are non-negotiable filters
— violating one is a failed run even if everything else is perfect. Before profiling anyone, query
persistent memory and gather every rule that could touch this task:

```
mem0_search("clothing fabric material preferences")   # also: gifts, shopping, brands, retailers
mem0_search("shopping email format requirements")
```

Also read the injected `memory` / user-profile block already in context. Restate the rules you
found at the top of the checklist (§3) so they're visible, and treat each as a hard gate in §5 and
§8. Don't hardcode the rules here — look them up fresh each run, because they change.

These two rules work together: **encode the mechanics, leave out the specifics.** "This retailer
marks a sold-out size with `--unavailable` on the size label" belongs in the skill forever. "Size 5T"
does not belong in it at all.

## Which track am I on?

| The ask | Track | Shape of the answer |
|---|---|---|
| A season of clothes for one or more people | **Wardrobe** (§3–§6) | A checklist, then one cart per person |
| One outfit for a dated event | **Occasion** (§3–§6, small) | One cart, options, deadline-driven |
| A gift for someone | **Gift** (§7) | 3–5 distinct *directions*, each costed |

All three share: profile the person (§1–§2), browse and verify (§8), build and send (§9–§10).

## Run it end to end

The user typically hands over the task and walks away ("don't wait for me, make educated
guesses"). Take that literally: make reasonable assumptions, note them in the output, and
finish. Don't stall on ambiguity you can resolve yourself.

**But do ask when the answer would change the whole shape of the output** — a budget band, or
whether a birthday is a milestone. One batched round of questions up front beats delivering the
wrong thing. Also ask for anything personal the skill can't know and the records don't hold:
recipients' email addresses, which stores the user actually shops, the budget. In the first gift
run, asking surfaced the recipient's serious side pursuit, which no amount of database mining had
revealed and which redefined every option.

---

## 1. Profile the person

For **clothing**, gather per person: age, current measurements (height/weight for kids), what they
do all day (school, daycare, hybrid office, at home), the local climate for that season, foot
notes, and any medical/orthopedic constraints.

For a **gift**, gather: the relationship (which sets the budget band as much as anything), age and
whether this birthday is a *milestone*, what they're actually into, what they already own, and who
else is giving — plus household context, since a gift often lands in a shared home.

**Don't guess at any of this, and don't assume the last run's answers still apply.** If a personal-
records MCP is connected (Pebbleway, for instance), that's the source of truth — it holds people,
children, measurements, clothing sizes, and health records:

```
mcp__pebbleway__query_graph   # find the person / child nodes and their properties
```

If no such tool is available, just ask the user for the handful of facts you need. The skill works
either way; it simply never carries them itself.

**The graph is good at relationships and thin on interests.** It will tell you who someone is
married to, where they live, and what car they drive; it usually won't tell you what they'd love to
be given. So for gifts, treat Pebbleway as step one of many, and expect to ask the user or read a
social profile. Widen the net before concluding there's nothing: search the name, check the shared
household and partner, and look for an `interests`/`hobbies` property — then ask.

**A birth year with no birthday is a milestone waiting to be missed.** Compute the age the person
is turning. If it's a round number, say so and confirm — it changes the budget and the whole tone
of the gift. In the first gift run the record had no `birthday` property at all, only a birth year
buried in a free-text notes field, which made a milestone birthday easy to overlook entirely.

**Names may legitimately differ across contexts.** A record name, a family name, and a stage or
professional name can all be correct for one person. In India, for instance, the name on a
passport and certificates often pairs a given name with a patronymic-style second name, while the
family is known socially by its surname — both are that person's real name, and neither is a typo
for the other. Don't "fix" the graph on this basis. Use the name that fits the context — the
professional or stage name on anything public-facing.

**Distrust a stored size; trust a stored measurement.** Sizes go stale as kids grow, and they're
often entered wrong. In the first run a preschooler's `shoe_size` was recorded as `4`, but US 4C is
an ~18-month-old's shoe — off by years. Recompute from measurements, and patch the record when you
find an error.

Also mine: school/daycare websites for their actual requirements (indoor shoes, spare sets,
outdoor-in-all-weather policies, label-everything rules), and the user's own notes.

**Ask about dated events in the season, not just daily activities.** Graduations, weddings,
picture day, Diwali, family photos and religious occasions each need a specific outfit and come
with a hard deadline that ordinary wardrobe items don't have. Check the calendar
(`mcp__pebbleway__get_upcoming_events`) and the school newsletter. The first run missed a child's
graduation two weeks out — the only dressed-up options on the list were an oxford and a polo, both
under-dressed for a ceremony. Surface these early: they're the items where shipping time can
actually make you miss the date.

**Personal data stays out of the artifacts.** Never put PII from the records (SINs, health-card,
passport numbers, medications) into a shopping list, markdown file, or email. Nor into this skill:
if a run teaches a lesson worth keeping, write the *lesson* into the skill and leave the names,
sizes, and addresses in the run's own output files.

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

- **Apply the standing preference gates first (from step zero).** Any hard rule the user holds —
  fabric/material composition, brands to avoid, fit requirements — is a filter, not a nice-to-have.
  A piece that violates one is out, however good it looks. For a fabric rule especially: this
  removes whole product lines (many performance/athleisure ranges are predominantly synthetic), so
  bias the palette and store routing toward lines that can actually clear the bar before you fall
  in love with a specific piece.
- Pick a **palette** and state it: neutral base, two warm counterpoints, one light knit so it
  doesn't go funereal.
- Make it **cross-match**: every top should work with every bottom. Say that it's deliberate.
- Prove it with **"Three outfits this makes"** — three named scenarios at real temperatures.
  This is the single most convincing part of the output.
- Give a **priority subset** for anyone who blanches at the total: the 3–4 pieces that cover
  most of the season, with their sum. Note which big-ticket item can wait for a sale.
- Separate the *workhorse* from the *nice thing* explicitly, and let the workhorses be cheap.

## 6. Store routing

**Route by role, not by brand.** If the user names their stores, use those. If not, pick retailers
that serve the user's own country and price level, and say which you chose and why. The roles that
matter:

| Who | What the store needs to be | Why |
|---|---|---|
| Kids, nicer pieces | A mid-market chain with real occasion clothes | Picture day, places of worship, family occasions |
| Kids, play clothes | A cheap, resilient chain | A ruined knee should cost $12, not $40 |
| Adults | A department store with decent house brands | Coherent capsules at sane prices |
| Anyone, fallback | A large marketplace | Gap-fillers and anything niche |

The recipes in `references/retailer-recipes.md` cover the Canadian chains used so far (Gap, Old
Navy, Simons, Amazon.ca). They're extraction recipes, not recommendations — for a user elsewhere,
work out the equivalent and add a recipe.

Watch for sales — a chain running ~50% off is the difference between two children's wardrobes at
$850 and at $1,600. Say when pricing won't hold.

## 7. Gifts: find several directions, then recommend one

A gift ask is not "find a product." It's "work out what this person would love, in a few genuinely
different ways, and price each." The user picks a *direction*; you make each one real.

**Find the one true thing first.** Before shopping, find the thing the person is currently pouring
themselves into — a craft they're pursuing, a sport they've taken up, a house they're renovating.
Everything good flows from that. A gift aimed at it beats an expensive gift aimed at nothing. If
you can't find it from the graph, a social profile, or the user, say so plainly rather than
defaulting to generic.

**Then generate distinct dimensions, not variations of one idea.** Five microphones is one
direction. A useful spread looks like:

| Dimension | What it is | Why it works |
|---|---|---|
| **Experience / presence** | Turn up to their gig, show, game, or class; tickets for the family | Usually the best gift and often the cheapest. Costs attention, not money |
| **The bottleneck tool** | The thing that fixes the actual weak link in what they're doing | Highest practical value — watch/read their work and diagnose it |
| **The full kit** | Two or three items that together change their output | For when one object feels thin |
| **The craft library** | The canonical books on what they're pursuing | Says "I take this seriously"; cheap enough to pair with another direction |
| **Identity / status** | Personalised or branded — treats their side pursuit as a real thing | Pure signalling, which is exactly why it lands |

Adapt the row labels to the person; keep the *spread* — one experience, one practical, one
generous, one cheap-and-thoughtful, one emotional.

**Sizing the gift.** Never assume a budget — **ask** for the band, then sanity-check it against
relationship, occasion, and milestone status. Closeness and milestone status both push it up; a gift
split across several family members pushes it up further. Once you have the band, make **every**
direction land inside it on its own, so the user can pick freely. Then say which you'd choose.

**Prefer the experience when it exists.** If they perform, compete, or exhibit, check whether
there's an event near the date — a live gig the night before their party is a better gift than any
object, and it makes an object handed over afterwards land harder. Check their socials for
upcoming dates, then verify the ticket page is really on sale.

**Say what you'd avoid, and why.** Name the default gift for that demographic and explain why you
skipped it: whisky stones and engraved barware are what you buy someone whose interests you don't
know, and you know theirs. That sentence is worth more than a sixth option.

## 8. Browse and verify — the part that actually takes the time

Use the browser MCP. See `references/retailer-recipes.md` for the working extraction
snippets, category IDs, and every failure mode hit so far.

**Read that file before you start browsing, and add to it as you go** (§11). If a retailer isn't in
there yet, you're about to learn how it works — capture the selector or the snippet the moment it
works, not at the end of the run when you've closed the tab and lost the details. If a recipe is
there but wrong, fix it; a stale recipe is worse than none, because it gets trusted.

The essentials:

- **Verify fabric/material composition against the live page, not the category grid.** When the
  user holds a material rule (e.g. a minimum natural-fibre percentage), the composition is a
  buyable-or-not fact just like size and stock — and it's almost never on the grid. Open the
  product page and read the fibre content ("Materials"/"Composition"/"Fabric & care" section, or
  the `material`/`description` field in the `ld+json` block). Compute the natural-fibre share
  (cotton, wool, linen, silk, cashmere, etc. vs. polyester, nylon, acrylic, elastane, viscose/
  rayon — note viscose is semi-synthetic, count it as synthetic unless told otherwise) and drop
  anything under the user's threshold. Record the composition in the cart JSON and surface it in
  the email next to each item, so the user can see the rule was honoured. If a page doesn't state
  composition, treat it as unverified and exclude it rather than guessing.
- **Simons**: parse the `application/ld+json` block on each product page for `name`, `brand`,
  `offers.price`, `offers.availability`. Category URLs bounce to the homepage under bot
  protection — use a **same-origin `fetch()` from an already-loaded tab** instead.
- **Gap / Old Navy**: a size is out of stock when its `<label for="pdp_buybox_dimension_…">`
  carries `fds_selector__label--unavailable`. Check the **child's exact size**, not just that
  the product exists. In the first run this caught **nine** pieces that looked fine on the
  category grid but were unbuyable in the size needed.
- **One tab per origin.** Cross-origin `fetch()` fails.
- Page-scoped helpers (`window.__V`) die on navigation — redefine after every navigate.
- A suspiciously cheap item (e.g. everything at `$9.99`) is usually **sold-out clearance**, not
  a bargain. Confirm `InStock` before believing a price.
- **Amazon search pages truncate titles to the brand** (every result reads just "DJI"). Get the
  real title, price, rating, and delivery date from the product page: `#productTitle`,
  `.a-price .a-offscreen`, `#availability`, `#mir-layout-DELIVERY_BLOCK`, `#landingImage`. Books
  sometimes leave the buy-box price element empty — read all `.a-price` nodes and take the
  format you mean.
- Note **`Only N left in stock`** from `#availability` and pass it through to the email. It's the
  difference between a recommendation that works tomorrow and one that doesn't.

### When there's a date, verify delivery — not just stock

For anything with a deadline, an in-stock item is not a buyable item. Read the delivery estimate
off the page and compare it to the date.

- **Made-to-order and personalised items are the trap.** A custom item can show "in stock" and
  still quote delivery *weeks* out — one personalised item advertised "ships in 4–5 days" and then
  quoted a window over three weeks past the deadline. Always read the actual date.
- If the best idea can't arrive in time, **keep it and label it**, rather than dropping it or
  pretending. Offer the workaround: print a mockup for the day, or pair it with something real.
- **Check a pickup fallback** when delivery is tight — big-box electronics, general-merchandise, and
  bookstore chains often stock the same item for same-day pickup, sometimes at a slightly different
  price or a newer model. Quote both, with the price difference.
- **Lead time beats price when the date cannot move.** Paying $5 more for the size that fits, or
  the option that arrives two days earlier, is the right call — say so explicitly.

If you delegate browsing to subagents, **do not let several of them share one browser** — they
deadlock in sleep-retry loops. Either drive the browser yourself or give agents disjoint,
short-lived jobs. If they do stall, their JSONL output files under the session dir can be
parsed to salvage verified products rather than re-running everything.

## 9. Write one markdown file per person

`00-CHECKLIST.md`, then `01-<name>.md`, `02-<name>.md`, …

Each file: brief + governing constraint, palette, sections by category with a `Qty | Piece |
Store | Price | Link` table, the reasoning under each section, "three outfits", the total,
the priority subset, and any not-ordered warnings (shoes) or availability caveats.

For a **gift**, the file is one per occasion (`<name>-<occasion>.md`): what you learned about the
person and where it came from, the five directions with their own tables and per-direction totals,
the recommendation, what you'd avoid, and anything adjacent worth doing (a related event to attend,
a missing record worth fixing).

For an **occasion outfit**, note what the existing wardrobe cart already covers so a piece isn't
bought twice — and if you reuse a row from another cart, keep its *original* store, product id, and
price. It's easy to copy a row and relabel it wrongly.

State the capture date and that stock was verified: *"Every item below was checked in stock in
&lt;size&gt; on &lt;date&gt;."*

## 10. Build and send the emails

Prices live in a JSON cart per person; the builder computes every subtotal and total. This is
deliberate — in the first run, three of four hand-written totals were arithmetically wrong.
**Never hand-write a total.**

```bash
# 1. Write one cart JSON per person (schema: references/cart-schema.md)
# 2. Build HTML from the shared shell — every email looks identical by construction
python3 scripts/build_emails.py carts/*.json --out-dir out/

# 3. Send each. Ask the user for the recipient addresses — never assume them,
#    and never hardcode them here.
python3 scripts/send_email.py \
  --to "$RECIPIENT" [--to "$SECOND_RECIPIENT"] \
  --subject "Fall 2026 shopping cart — <name> (<context>, size <size>)" \
  --html out/email-01-<name>.html
```

`build_emails.py` prints each computed total and cross-checks it against an optional
`expect_total` in the JSON, so a mismatch fails loudly instead of shipping.

**If the email presents alternatives rather than one list** — three outfit options, or five gift
directions, pick one — the builder still sums *everything*, so the grand total is arithmetic, not a
price. Don't fight this: set `expect_total` to that real sum so the guard rail keeps working, lean
on the per-section subtotals as the numbers that matter, and say so explicitly in both the opening
note and the footnote. Also give an actual recommendation; options with no opinion pushes the
decision back onto the user, which is the opposite of the job.

Let the guard rail do its job rather than pre-computing by hand: in the gift run `expect_total` was
hand-added and came out about $51 above the real sum, and the build failed loudly instead of sending
a wrong number. Take the computed figure, sanity-check it, and use it.

`send_email.py` reads SMTP credentials **at runtime** from a TOML file (default
`~/.config/owlpost/accounts.toml`, overridable with `--config`; account name via `--account`).
**Never hardcode or print a password, and never commit one.** The script APPENDs to the Sent folder
manually because some providers' SMTP (iCloud among them) doesn't. Any connected mail MCP that sends
HTML works as an alternative.

Email conventions, all enforced by the shared shell in `assets/email-template.html`:

- One email per person or per occasion, **identical formatting** across all of them.
- Hyperlink every item name to its product page; show the price beside it.
- `×N` quantity badges where quantity > 1.
- Per-section subtotals and a single prominent total.
- **A thumbnail on every item** (`image` in the cart JSON). The user asked for these explicitly —
  they make the email browsable without opening 20 tabs. Collect image URLs while you're already
  on the rendered category grid; going back for them afterwards means re-navigating every page.
  See the image section of `references/cart-schema.md`, including the two pre-send checks
  (every URL returns `image/*`; the images are distinct from one another).
- Banner at the top holding the facts that shaped the list: the size derivation for a child, or
  for a gift the occasion, budget band, the angle you found, and the deadline.
- Callout blocks: info (green) for design notes, warn (amber) for measure-feet-first, delivery
  risk, and availability caveats.
- Footer noting prices were captured on a date and will drift.

Before sending, verify: no `{{PLACEHOLDER}}` survives, link count is sane, and — per the
user's global instruction — **no Claude/AI attribution anywhere** in the emails or in any
commit or public artifact.

## 11. Write back what you learned — every run

**This skill is meant to get better every time it runs.** Most of the wall-clock cost of a run is
figuring out how a site behaves: which selector holds the real price, why a category URL bounces,
what a sold-out size looks like in the DOM. That knowledge is expensive to obtain and nearly free to
record. If you finish a run and the skill is unchanged, you've thrown that away and the next run pays
for it again.

So treat editing the skill as **part of the task, not a favour** — before you report back, not "some
day". Watch for these while you work, and write each one down as it happens:

| You just… | Write it into |
|---|---|
| Worked out how to read a price/stock/image/delivery date from a site | `references/retailer-recipes.md` — a new `## <Retailer>` section |
| Hit a failure and found the workaround (bot protection, empty grid, dead helper) | The same retailer's section, as a **Failure modes** bullet |
| Found a selector, category ID, or API endpoint that works | The retailer's section, marked with the date you verified it |
| Learned something true of *every* site | "Rules that apply everywhere" at the top of the recipes file |
| Made a judgement error a rule would have prevented | `SKILL.md`, as a rule at the relevant step |
| Changed the cart JSON or the builder's behaviour | `references/cart-schema.md` |
| Completed a run worth imitating | A short `references/example-run-*.md`, anonymised |

**A recipe is only useful if it's specific.** Not "Retailer X is hard to scrape" but the selector,
the URL shape, the exact class name, the snippet that worked — enough that the next run can paste it
and move on. Date-stamp it: sites change, and a reader needs to know whether to trust it or re-verify.

Record the **failures too**, not just the wins. "Category pages bounce to the homepage under bot
protection; use a same-origin `fetch()` from an already-loaded tab" saves more time than any
successful selector, because otherwise the next run spends twenty minutes rediscovering the wall.
The same goes for dead ends: if an approach *can't* work, say so, so nobody retries it.

Three constraints on what you write:

1. **Mechanics, not specifics** — per the rule at the top. A recipe describes the *site*. It never
   contains a person's name, size, address, budget, or a real order.
2. **Recipes, not endorsements.** Adding a retailer's recipe doesn't mean the user shops there. Say
   which country and segment it serves, so someone elsewhere knows whether it applies.
3. **Don't let it sprawl.** Prefer editing an existing rule over appending a near-duplicate. If a
   general rule now covers three retailer-specific notes, promote it and delete the three. The
   recipes file is a working reference, not a changelog.

Then **tell the user what you changed and why**, in a line or two of your report — they can veto it,
and they should know the skill isn't the same as it was this morning. If a change is bigger than a
recipe (a new track, a builder change), say so plainly rather than slipping it in.

## Report back

Give a table of item counts and totals, the grand total, how sizes were derived and verified, and
the 2–3 things needing the user's attention (shoes not ordered and why, sale timing, sizes that
sell out fast, a deadline that can't be met). Be concrete about what was *not* bought and why —
winter parkas in August, footwear needing in-person fitting, a custom item that can't arrive.

For a gift, lead with **what you found out about the person** and where it came from — that's the
part the user can't get anywhere else — then the directions and your recommendation.

Close with **what you taught the skill** (§11): the recipes, rules, or failure modes you wrote back,
in a line. If you learned nothing new, say that too — it means the references are holding up.

State your own mistakes plainly if any were caught mid-run (a mislabelled row, a guessed image URL
that 404'd). The guard rails exist because errors happen; hiding them wastes the guard rails.

## Known-good references

Both are anonymised write-ups of real runs — read them for the method and the failure modes, not for
anyone's sizes or budget.

- `references/example-run-2026-fall.md` — the wardrobe run: 4 people, 73 items, with the sizing
  derivations, the graduation follow-on, and each error caught along the way.
- `references/example-run-2026-gift.md` — the gift run: a milestone birthday, five directions, and
  how the deciding fact came from asking the user rather than from the records.
- `references/retailer-recipes.md` — extraction snippets per retailer, and every browser failure
  mode hit so far.
- `references/cart-schema.md` — the cart JSON the builder consumes.
