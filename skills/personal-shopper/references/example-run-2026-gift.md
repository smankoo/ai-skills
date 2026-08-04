# Example run — a milestone 40th, Aug 2026

The first **gift** run of this skill, five days before the party. Worth reading for how the
deciding fact was found, because it wasn't in the database.

Details are generalised here — the recipient is a third party, and this file is public.

## The ask

> "[His] birthday party is this Sunday (that's not when his birthday is, just the party) and we
> need a gift, so I need the same kind of support from the skill — look for gifts in 5 different
> dimensions. Look him up in Pebbleway, figure out what 'size' of gift is appropriate for this
> occasion, then figure out top 5 kinds that make sense, and 'shop' for them and email me and my
> wife."

Note the two-part framing: *size* the gift first, then find five *kinds*. The dimensions are the
deliverable — not five products.

## What the graph gave, and what it didn't

`query_graph` on the name returned plenty: the relationship (brother-in-law), who he's married to,
one child, a city, a vehicle with a tow hitch, and party-invite edges. What it did **not** contain:
a single interest, hobby, or preference. The `person` record had no `birthday` property at all —
only a birth year inside a free-text notes field, and an empty timeline.

Two lessons, both now rules in `SKILL.md` §1:

1. **A birth year with no birthday is a milestone waiting to be missed.** The year implied he was
   turning **40**. That reframed the whole brief, and it was one `get_upcoming_events` call away
   from being missed entirely (the party isn't in the calendar, and the party date isn't his
   birthday).
2. **The graph knows relationships, not interests.** Searching WhatsApp for the invite found
   nothing either. After exhausting the automated sources, the right move was to *ask* — which is
   where the entire run turned.

## The fact that changed everything

The user answered the budget and milestone questions and added, unprompted, that the recipient is
pursuing standup comedy hard — with a link to his Instagram profile.

From the profile and one linked post:

- A bio identifying him as a standup comic
- ~3.2k followers, ~270 posts, a YouTube special with a few hundred subscribers
- Highlight reels titled "Relatable" and **"Opening Acts"**
- Material is family-and-immigrant observational
- **He was hosting a show the night before the party** — a specific venue, 8 PM, the Saturday

That last item was the single most valuable finding of the run, and it came from reading a tagged
poster image's `alt` text on his profile grid. Verified all the way to a live Eventbrite listing
with `availability: InStock` and a ~$28–$49 ticket range.

**Rule:** if the recipient performs, competes, or exhibits, look for an event near the date. Showing
up beats an object, and it makes an object handed over afterwards land harder.

## The five dimensions

| # | Dimension | Pick | Cost |
|---|---|---|---|
| 1 | Experience / presence | 4 tickets to the show he was hosting | $100 |
| 2 | The bottleneck tool | A wireless lav mic — his clips' weak link is audio, not video | $139.00 |
| 3 | The full kit | Phone gimbal + ring light | $149.98 |
| 4 | The craft library | Three books on writing and performing comedy | $80.67 |
| 5 | Identity / status | A custom mic flag printed with his handle | $40.99 |

Recommended **1 + 4** (~$125): watch him host the night before he turns 40, then hand him a book
about the craft. The gift is the turning-up; the book is the thing to unwrap.

Also stated what to avoid — "whisky stones and engraved barware are what you buy someone whose
interests you don't know" — which is worth more than a sixth option.

## Errors caught (each is now a rule)

| Error | Fix |
|---|---|
| `expect_total` hand-added to $561.61; real sum was $510.64 | The guard rail failed the build. Never hand-add — take the computed figure |
| A guessed `m.media-amazon.com` image URL returned **404** | Fetch every image before sending; read `#landingImage` from the real product page |
| The Eventbrite image URL 403'd to a bare `fetch` | Its signature covers every query param — use the signed URL byte-for-byte, unmodified |
| Amazon search results all showed a truncated title (just the brand) | Search pages truncate; open the product page for title/price/delivery |
| The custom mic flag quoted delivery **three-plus weeks out** | Made-to-order items show "in stock" and still miss the date. Keep the idea, label it, offer a workaround |
| Assumed the record name and the family surname disagreeing was a data error worth fixing | Indian naming: an official record name and a family/stage name legitimately coexist. Don't "fix" the graph |

## Two smaller things

- One book showed **"Only 1 left in stock"** — passed through to the email, because it changes
  whether the recommendation still works tomorrow.
- Checked a **pickup fallback**: a big-box retailer had the newer mic model at a dollar more for
  same-day pickup, quoted alongside the marketplace's next-day price, since the user asked to see
  both.
