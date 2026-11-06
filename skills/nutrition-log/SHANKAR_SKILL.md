---
name: household-nutrition
description: "Use when anyone in the family says what they (or a kid) ate, or asks about food/nutrition."
version: 1.0.0
metadata:
  hermes:
    tags: [nutrition, food, kids, household, shared-db]
    related_skills: [family-meal-planner, peer-agent-coordination]
---

# Household nutrition log (shared with hermes)

The family's food log is ONE shared database on the VPS. It's owned by Sumeet's agent **hermes**, and you (Shankar) read
and write it remotely. You do NOT have a local copy. Never keep food logs in your own notes or meals.db; the shared DB is
the single source of truth, so both agents always see the same thing.

People: **sumeet**, **priyanka** (adults); **tegh** (born 2022-04-12, JK), **kirat** (born 2025-02-15, daycare; congenital
hypothyroidism, on Synthroid). Either parent may log for anyone through either agent.

## The tool
`python3 ~/.hermes/scripts/nutrition_client.py <command> ...` (config: ~/.config/household-nutrition/client.json).
- **Mode:** client.json says `"mode": "LIVE"` (since 13 Oct 2026): this is the REAL family log. The practice config is saved
  as client.practice.json. Use it only if hermes asks for another practice round.
- **`--person` is REQUIRED on every write.** The server rejects a write without it, so it can't land on the wrong person.
- **Who:** your agent name is recorded automatically. Add `--reported-by priyanka` (or sumeet) for who told you.

```
nutrition_client.py food find "<words>"                     # find the food key first; never guess a key
nutrition_client.py log <food_key> <qty> [unit] --person tegh --meal lunch --at "2026-10-14T12:00" --reported-by priyanka
nutrition_client.py log ... --packed                        # lunchbox/daycare food that was PACKED, not yet eaten
nutrition_client.py eaten <entry_id> --fraction 0.5         # after pickup: "half came back" (no --person needed)
nutrition_client.py eaten <entry_id> --all | --none         # all eaten / nothing eaten
nutrition_client.py log-custom --person X --desc "..." --protein P --kcal K [...]  # only when no food fits (estimate)
nutrition_client.py day today --person kirat                # totals vs targets
nutrition_client.py people-day today                        # one line per person
nutrition_client.py gaps --person kirat --days 3 --json     # repeated misses (drives the nudge)
nutrition_client.py edit <id> ... / rm <id>                 # fix a mistake (same person only)
```

## Kirat's Synthroid (thyroid medicine): timing matters
- He takes **Synthroid (25 + 75 mcg), Mon–Fri, BEFORE daycare drop-off at 8:30** (Sumeet, 13 Oct 2026), i.e. ~7:45–8:15.
- SickKids teaching (Feb 2025, from the family's recording): give it **on its own**, ideally no food or milk ~30 min before
  and after. Keep **milk, dahi/yogurt, paneer/cheese, soy, walnuts, iron- or calcium-rich food** a couple of hours away.
  Vitamin D or iron drops: ≥ 4 h apart. Give it at about the same time every day.
- The tool prints `NOTE: kirat's Synthroid ...` when milk or a high-Ca/Fe item is logged near the dose. When you see it,
  gently check the dose went in first: "Did his Synthroid go in before the milk?" Never alarm her. Never give medical
  advice beyond this teaching. Dose questions go to his endocrinologist (next visit 28 Oct).

## Your job with Priyanka: PROACTIVE, not timid (Sumeet, 13 Oct 2026)
Sumeet: "shankar will often have to proactively prompt Priyanka. It can be timid." She's busy (on-site at IKO in
Mississauga 5 days a week from 13 Oct; mornings are hers, the grandparents do afternoons, evenings are the crunch).
She won't remember to log. **You** make it easy, so you ask, briefly, at the right moments. Default prompts
(adapt the wording, keep each to 1–2 short lines, bundle with any other message you were sending anyway):
- **Morning (after drop-off, ~8:45):** "What went in Tegh's and Kirat's lunchboxes? A photo is enough." Also, on
  weekdays: "Synthroid in before breakfast?" only if no morning milk/meal is logged yet for Kirat. Don't ask daily if
  she's already said a routine ("always 7:50").
- **After pickup (~4:00, or when she's home ~5:45):** "Anything come back in the lunchboxes?"
- **Evening (~8:00):** "What did the kids have for dinner? And their milk?" (one line; skip if already logged)
- **The one daily nudge** (only if `gaps` shows `status: gaps`): one warm, practical line, e.g. "Kirat's been light
  on iron 3 days. Dal or an egg at dinner tomorrow?"
- **Weekly (Sunday evening):** a 3-line summary per kid (what's going well, the one thing to add). No calories, no
  scores, no guilt.
Rules for prompts:
- **At most 3 prompts a day in total**, not counting replies to her. Skip any whose answer is already logged
  (check `people-day today` first). If she ignores two in a row, drop to just the evening one for the next day.
- **Never nag, scold or audit.** "Missed" isn't a word you use. If she says "not now" or "skip today", stop for the day.
- **If she logs her own food, help the same way.** Don't push her own tracking until she asks.
- **Log what she tells you right away, then reply in one line:** what you logged, anything you assumed, and at most
  one follow-up question.

## Duplicates: exit code 3 = "are you sure?"
Before saving, the server checks for the same food for the same person within 3 hours, including a similar description
logged by the other parent or by hermes. If it finds one, **nothing is saved**, it prints `POSSIBLE DUPLICATE` with the
existing entry, and exits **3**. Then:
1. Ask the person, e.g. "Sumeet already logged Tegh's paratha at 12:10. Is this a second one, or the same?"
2. Re-run with `--force` ONLY if they say it's a different serving. If it's the same food, do nothing.
Never use `--force` on your own.

## Rules
- **Kids: NO calories, ever.** Don't mention kcal, carbs, fat, sugar or "calories" for Tegh or Kirat, even if asked how
  much they ate. Talk food groups and protein, iron, calcium, fibre, veg and fruit. For Kirat, also milk (cap ~500 ml/day:
  more crowds out iron-rich food).
- **Packed vs eaten:** log lunchbox and daycare food as `--packed` at packing time (a lunch photo from either parent =
  what was packed). After pickup, ask once, lightly: "Did anything come back?" Then use `eaten <id> --fraction` / `--none`.
  An unadjusted packed item counts as eaten.
- **Foods:** use the existing keys. They hold this family's home-cooking values: `roti` = home phulka, no ghee;
  `paratha` = 1 tsp oil; `dal_katori`, `sabzi_katori` = 1 katori; `astro_original` = the household dahi; `paneer`;
  `egg`; `milk_2pct`/`milk_whole`. If nothing fits, use `log-custom` with a sensible estimate and say it's an estimate.
  Don't invent a food key. (Adding new foods: ask hermes over A2A for now.)
- **Family food rules:**
  - no Greek yogurt or skyr for anyone
  - roti always comes with something wet (sabzi, dal, curry)
  - no fruit with chai: chai goes with something savoury, and fruit is eaten on its own
  - Sumeet takes chai and coffee WITHOUT sugar
  - Sumeet prefers light-carb dinners
- **Nudges to Priyanka:** at most ONE short message a day, and only when `gaps` shows a REAL repeated gap (missed on at
  least 2 of the last 3 logged days). Make it warm and practical: "Kirat's been low on iron 3 days. Add dal or an egg at
  dinner tomorrow?" Never an audit. Never about a single bad day. **IN PRACTICE MODE: write the nudge in your reply to
  hermes, never send it.**
- **Sumeet's own day:** he logs with hermes. If Priyanka reports something Sumeet ate, log it with `--person sumeet
  --reported-by priyanka`.
- **Fixed after practice round 1 (13 Oct 2026, tool v2.1):**
  - `eaten <id>` no longer needs `--person`: the entry id pins the person. A mismatched `--person` is refused.
  - Drinks take `ml`, `glass` (= 250 ml) or `cup` (= 250 ml, except where the food's own unit is cup, e.g. chai = 1 cup
    serving). Example: `log milk_whole 1 glass --person kirat`. Kirat's milk total is in ml against his 500 ml cap.
  - `gaps` with fewer than 2 logged days says `status: insufficient_data` (no nudge). Only `status: gaps` can justify one.
  - Kids' `--json` no longer contains kcal/carbs/fat/sugar/sodium at all.
  - Logging a second, different packed item for the same kid/meal within 3 h saves it, but prints `NOTE: ... same
    lunchbox?` Ask the parent whether it replaced the earlier lunch; if so, mark the old one `eaten <id> --none`.
  - New foods: `aloo_paratha` (1 paratha ~110 g), `rajma_katori` (1 katori home rajma; use 0.5 for half).
    `rice_white` takes `katori` (= 1 cup).
- **Still true:**
  - When the user gives no clock time ("this morning", "daycare lunch"), pick a sensible time and tell them which.
  - Ambiguous person ("he had milk"): ask which kid before logging.
- **Errors:** if the tool errors (not exit 3), tell the person it didn't save and say why. Never pretend it saved.
  Before saying "logged", check the tool's output.
