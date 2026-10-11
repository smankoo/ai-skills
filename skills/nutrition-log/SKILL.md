---
name: nutrition-log
description: >
  Use when Sumeet says what he ate or drank, sends a food/label/receipt photo, asks "how am I doing
  today", "what should I eat", protein/fibre/calorie questions, or for any daily nutrition guidance.
  Logs every food into a local SQLite DB with full nutrients (kcal, protein, carbs, fat, sat fat,
  fibre, sugar, sodium, veg/fruit servings, water) and coaches him across the day against all targets.
---

# Nutrition log (Sumeet's food + nutrient tracker)

The single source of truth for what Sumeet ate is **`~/.hermes/data/nutrition.db`**. It is driven by
`scripts/nutrition.py` (stdlib-only CLI, 25 unit tests). Everything goes in here: not only protein.
mem0 gets one short daily line (so Magnus can see it). The DB holds the detail.

```bash
N="python3 ~/.hermes/skills/sumeet/nutrition-log/scripts/nutrition.py"   # symlinked from ~/.ai-skills
$N summary                     # ≤8-line block vs ALL targets + gaps: what you reply from
$N day today|yesterday|YYYY-MM-DD   # entries with ids + full target table
$N food find "dal"             # look up a key before logging
$N log KEY QTY [UNIT] --meal lunch --at "15:14" [--desc ".."] [--confidence low] [--source photo|magnus|label]
$N log-custom --desc "restaurant thali" --protein 30 --kcal 800 --carbs 90 --fat 35 --satfat 12 --fibre 8 --veg 1.5
$N edit ID --qty 2 | --at .. | --meal ..      $N rm ID [ID..]
$N water 500                   $N week          $N targets / targets set KEY VAL
$N body add weight_kg 80.6 --source withings  $N body latest
$N food add --key K --name N --basis 100g|serving [--serving-g G --unit U] --kcal .. --protein .. --carbs .. --fat .. --satfat .. --fibre .. --sugar .. --sodium .. [--veg ..] [--fruit ..] --source "label|CNF code"
```
Units: `g`, `serving`/`x`, or the food's unit (`egg`, `roti`, `katori`, `scoop`, `carton`, `bar`, `cup`). Plurals work.
Entries **snapshot** nutrients, so fixing a food row later does not rewrite past days. Re-log if needed.

## Targets (seeded 2026-10-11; ~80.5 kg, 180 cm, 39 y, lifting + cricket, mild fat loss)
| Target | Value | Why |
|---|---|---|
| kcal | 2300–2600 | maintenance ≈2,600–2,800 when active; a small deficit |
| protein | ≥140 g | his stated target (≈1.75 g/kg). Never say 130 |
| carbs | 250–330 g | fuel for lifting/bowling; don't cut roti/rice |
| fat | 65–85 g | |
| sat fat | ≤25 g | paneer (15 g/100 g), ghee, pastry, Quest bars are the usual culprits |
| fibre | ≥32 g | his usual gap |
| sugar | ≤50 g | |
| sodium | ≤2300 mg | restaurant food, pickle, papad, packaged snacks |
| veg ≥5 / fruit ≥2 servings | | 1 veg serving ≈ 75 g (½ cup) cooked/raw; 1 fruit = 1 medium piece |
| water | ≥3 L | creatine + high protein |
Change them with `targets set` only when he asks, or when his weight changes by more than 3 kg. Record it in Pebbleway self (`nutrition_targets`).

## Workflow every time he mentions food
1. **Gather the day first.** He sometimes tells **Magnus** instead. Before reporting totals, check
   `$N day today`, mem0 ("<date> food log"), and `sumeet_chat_today.py`. If the day looks thin, A2A
   magnus ("anything he ate today? compact list"). Do not invent meals or timings: ask if it's unclear.
2. **Log each item** with the right key. Photos: read the label (`vision_analyze`) and `food add` a
   new label-sourced row if the food isn't in the DB (one row per product; `basis serving`). Home
   dishes: use `dal_katori`/`sabzi_katori` or compose from ingredients (e.g. chicken curry = 100 g
   `chicken_thigh` + 1 tsp `oil_canola` + 0.5 `sabzi_katori`). Restaurant/unknown: `log-custom`
   with `--confidence low`. Use `--at` with his stated time (the message timestamp is fine).
3. **Reply** from `$N summary`: running totals for protein, kcal and fibre, then the 1–2 biggest
   gaps and **one concrete next-meal suggestion that fits his rules** (below). Keep it short.
4. **mem0:** keep ONE line per day, updated rather than duplicated: "Sun Oct 11 food log: P98 kcal960 fib14
   veg0 …, entries: …". Magnus reads mem0.
5. Corrections ("no, I had the shake after the whey") → `edit`/`rm` immediately and re-summarise.

## Guidance over the day (no extra pings unless he asks)
- **Gym days:** about 25–40 g protein in the 2 h before or after training. Suggest the session time based on
  when he last ate (2–3 h after a meal is ideal).
- **By ~3 PM** he should be at ≥50% protein and have had ≥1 veg serving. If not, steer lunch/snack.
- **Evening:** close the biggest gap with real food first, then whey/shake. Skip bedtime whey on
  big-chicken days. Before bed, if veg/fruit is 0, suggest fruit or a quick salad rather than nothing.
- **Explain the tradeoff** when he picks convenience food: bars and shakes give protein but no veg,
  micronutrients or fibre variety (Quest = added fibre plus sweeteners and sat fat); bakery
  puffs and samosas are mostly refined flour and fat; high protein with no veg hurts gut and heart health and leaves him hungry.

## His food rules (hard)
- **Never Greek yogurt** (hates it). Plain dahi (Astro 3%) with whey is fine.
- Roti always goes with something **wet** (dal, sabzi with gravy, curry). Dry boiled eggs are a standalone snack only.
- Chai: no second drink alongside. Paneer with chai is fine.
- Chronic hives: don't suggest new supplements casually. Supplements must be **NSF Certified for Sport** (labels are distrusted: use personal-shopper `cert_lookup.py`).
- Don't infer stock from photos ("I have plenty").

## Body data (weight etc.)
- His weight is about **80–81 kg** (2026-10-11). Fitbod's 84 kg is stale. The latest value is kept in `body` + Pebbleway self (`weight_kg`).
- **Apple Health is NOT reachable from the VPS or iMac directly.** HealthKit lives on the iPhone,
  macOS has no Health store, and there is no export API. Options, in order of ease:
  1. **Withings API.** He owns a Withings Body Smart scale (bought Sep 2026) that syncs to Apple Health.
     A Withings developer app plus a one-time OAuth consent lets a cron pull weight and body-fat% into `body`.
  2. **iOS Shortcut automation**, run daily on the iPhone: "Find Health Samples (weight/steps/active energy, last 1 d)" →
     POST JSON over the tailnet to a VPS endpoint, or save to iCloud Drive, which Magnus can read.
  3. The "Health Auto Export" app (paid) running a REST automation to the same endpoint.
  Until one is set up, ask him or use the latest `body` value. Never guess.

## Data sources for the food table
- Generic foods: Health Canada **Canadian Nutrient File** API. Nutrients come from `nutrientamount/?id=<code>&type=json`;
  ids 208 kcal, 203 protein, 205 carbs, 204 fat, 606 sat fat, 291 fibre, 269 sugar, 307 sodium.
  Food list: `food/?lang=en&type=json`. Seed list: `scripts/seed_foods.json` (each row's `source` holds the code).
- Products: the label first, then Open Food Facts. Household dish estimates are in wiki `concepts/household-dish-protein.md`.

## Pitfalls
- Raw vs cooked weight: CNF meat rows are **cooked, meat only**. If he says "200 g chicken" he means cooked
  pieces on his plate. Bone-in drumsticks are about 70% edible meat.
- `egg` is per large egg (50 g); `egg_omelette` row includes cooking fat (higher sodium).
- `--json` on any command is available for scripts. Exit code is non-zero on unknown food/unit/id,
  and it suggests the closest keys.
- The DB lives outside the repo (personal data). Never commit it.
