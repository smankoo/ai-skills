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
- **Mode:** if client.json says `"mode": "PRACTICE"`, you are on a practice copy. Writes there never touch the real log.
- **`--person` is REQUIRED on every write.** The server rejects a write without it, so it can't land on the wrong person.
- **Who:** your agent name is recorded automatically. Add `--reported-by priyanka` (or sumeet) for who told you.

```
nutrition_client.py food find "<words>"                     # find the food key first; never guess a key
nutrition_client.py log <food_key> <qty> [unit] --person tegh --meal lunch --at "2026-10-14T12:00" --reported-by priyanka
nutrition_client.py log ... --packed                        # lunchbox/daycare food that was PACKED, not yet eaten
nutrition_client.py eaten <entry_id> --fraction 0.5         # after pickup: "half came back"
nutrition_client.py eaten <entry_id> --all | --none         # all eaten / nothing eaten
nutrition_client.py log-custom --person X --desc "..." --protein P --kcal K [...]  # only when no food fits (estimate)
nutrition_client.py day today --person kirat                # totals vs targets
nutrition_client.py people-day today                        # one line per person
nutrition_client.py gaps --person kirat --days 3 --json     # repeated misses (drives the nudge)
nutrition_client.py edit <id> ... / rm <id>                 # fix a mistake (same person only)
```

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
- **Errors:** if the tool errors (not exit 3), tell the person it didn't save and say why. Never pretend it saved.
  Before saying "logged", check the tool's output.
