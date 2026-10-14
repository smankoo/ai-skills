---
name: nutrition-log
description: >
  Use when Sumeet says what he ate or drank, sends a food/label/receipt photo, asks "how am I doing
  today", "what should I eat", protein/fibre/calorie questions, or for any daily nutrition guidance.
  Logs every food into a local SQLite DB with full nutrients (kcal, protein, carbs, fat, sat fat,
  fibre, sugar, sodium, veg/fruit servings, water) and coaches him across the day against all targets.
---

# Nutrition log (the household food + nutrient tracker)

## HOUSEHOLD (v2, live since 2026-10-13): read this first
- **The app is standalone now:** github.com/smankoo/household-nutrition (private), checked out at
  `~/p/household-nutrition` with venv `.venv`. Its MCP server `household-nutrition-mcp.service` (user unit) runs on
  100.68.134.114:3425/mcp. Per-agent tokens are in `~/.hermes/secrets/nutrition_mcp_tokens.json` (hermes, shankar);
  the agent name becomes logged_by. **Use the MCP tools first** (`mcp_household_nutrition_*`: log_dish, find_food,
  day, summary, people_today, week, gaps, targets, edit_entry, mark_eaten, remove_entry, add_food, log_custom). Fall
  back to `nut` only if MCP is down. Code changes go in that repo (133 tests: `make test`), NOT in this skill's
  `scripts/` copy, which is now legacy (all three services run from the app repo's venv since 2026-10-13).
  Rebuild/IaC: the n8n-vps-iac hermes role, `--tags household_nutrition` (restore restic FIRST: the role refuses to
  start on a missing DB), plus docs/household-nutrition.md there. restic dumps a consistent copy to
  `~/.hermes/data/db-dump/nutrition.db` before each hourly backup, so restore from that.
- **Log with `nut`** (`~/.local/bin/nut` → `scripts/nut`). One command per dish, never hand-built nutrition.py
  calls or raw SQL (Sumeet, 2026-10-13: "Shouldn't you have some handy Tools/skill to update the db instead of rawdogging
  it every time?"):
  - `nut eat <person> "<dish>" food:qty[:unit] ... [--at 15:30] [--meal snack] [--packed] [--by priyanka]`.
    Ingredients of one dish don't count as duplicates of each other. The first item still runs the cross-parent check
    (exit 3 = ask "are you sure?").
  - `nut today` (everyone), `nut today kirat`, `nut find <text>` (food keys, no SQL), `nut fix <id> ...`, `nut rm <id>`.
    Anything else is passed straight through to nutrition.py.
  - It always drops a stale `NUTRITION_DB`. `--practice` uses the practice copy.
  - Missing food? `nut food add --key ... --basis 100g ...` with label/CNF numbers.
- **One shared DB** `~/.hermes/data/nutrition.db` for **sumeet, priyanka, tegh, kirat** (`person list`). Hermes writes
  locally. **Shankar** (iris) writes remotely through `scripts/nutrition_server.py` (systemd user unit
  `household-nutrition-live`, 100.68.134.114:3420, iris-only via ufw + allowlist, token file
  ~/.hermes/secrets/nutrition_tokens.json). Practice copy: `nutrition_practice.db` on :3421 (`-practice` unit).
  Shankar's own skill lives on iris at `~priyanka/.hermes/skills/productivity/household-nutrition/SKILL.md`. A mirror is
  in this repo as `SHANKAR_SKILL.md`; edit it here, then push to iris with the ssh + sudo -u priyanka cat recipe.
- **Every write takes `--person`.** Default is sumeet locally. Add `--reported-by sumeet|priyanka`.
- **Duplicates:** exit 3 = POSSIBLE DUPLICATE, nothing written. Ask, then `--force` only if it's a different serving.
  Different known foods are never duplicates, so the ingredients of one dish log fine.
- **Kids** (tegh, kirat): never talk calories. Targets are protein, iron, calcium, fibre, veg, fruit (+ Kirat milk ≤500
  ml). Lunchboxes: `log ... --packed`, then after pickup `eaten <id> --fraction F | --all | --none`. **When Sumeet
  sends a kid's lunchbox photo, log it `--packed`** so Shankar's 09:40 prompt to Priyanka stays quiet.
- **Kirat's Synthroid:** weekdays before the 8:30 daycare drop-off (meta `med_window:kirat`). Logging milk or a
  high-Ca/Fe item near it prints a NOTE (SickKids teaching, Feb 2025, ~/gdrive "Kirat's Birth/sickkids visit.txt").
- **Drinks:** `ml`, `glass` (250 ml) and `cup` work. `gaps --person kirat --json` → status gaps / on_track /
  insufficient_data.
- **Never reseed with `init`** on the real DB: it would overwrite hand-calibrated foods (chai, roti, whey). Use
  `seed_missing.py` to add new seed foods only.
- **Shankar's prompts to Priyanka** are crons on iris, max 3/day, "skip today" honoured: Mon–Fri 09:40 lunchbox +
  Synthroid; Mon–Fri 18:35 what came back; daily 20:00 dinner + milk + ≤1 nudge; Sun 19:30 summary.
- **Pitfall:** a stale `NUTRITION_DB` env var from a test silently points the CLI at a scratch file. Run `unset
  NUTRITION_DB` before real logging, and check `python3 -c "import nutrition;print(nutrition.db_path())"`.

# (Sumeet-specific usage below)

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

**Water is NOT tracked** (Sumeet, 2026-10-12: "I've had water. I obviously am not going to log each sip of water i take").
There is no water target. Never say "water not logged" or ask him to log water. `water N` still records an amount if he
volunteers one. A short hydration nudge is fine only when it's relevant (creatine started, a hot day, a long session).
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
3. **Reply format (Sumeet 2026-10-14: "hard to read... make it compact and add percentages"):** ONE line per target,
   `Protein 50/140g (36%)`, with a ✅ when hit and ⚠️ when over a limit; sat fat/sodium as `9/25g (36%)`. Then at most 3 short
   "next" lines with time + food + grams of protein. No prose paragraphs, no tables, no explaining fruit-sugar unless asked.
   Each line starts with its emoji (Sumeet asked 2026-10-14, chat updates only; the Mankoo Times keeps Phosphor icons):
   💪 Protein · 🔥 Calories · 🌾 Fibre · 🥦 Veg · 🍊 Fruit · 🧈 Sat fat · 🧂 Sodium · 🍬 Sugar (only if over) · 🍞 Carbs (only if asked).
   Next lines: ⏰ time, then food, then (+Ng).
   **Use the bar card (2026-10-14: "make the percentages into little progress bars"):** run
   `python3 ~/.hermes/skills/sumeet/nutrition-log/scripts/nutcard.py [person] [today|yesterday|YYYY-MM-DD]` and paste its
   output verbatim. Each group is TWO lines: `💪 Protein 50/140g` then the bar `▓▓▓▓░░░░░░` on its own line, so bars align in Telegram's proportional font, with a BLANK LINE between groups so each bar clearly belongs to its label (Sumeet 2026-10-14) (10 cells per row, ▓ filled/░ empty, ✅ goal hit, ⚠️ limit over). Never hand-draw bars. Sugar is left out
   because the DB counts fruit/milk sugar, which his limit ignores.
   Data comes from `$N summary`: running totals for protein, kcal and fibre, then the 1–2 biggest
   gaps and **one concrete next-meal suggestion that fits his rules** (below). Keep it short.
4. **mem0:** keep ONE line per day, updated rather than duplicated: "Sun Oct 11 food log: P98 kcal960 fib14
   veg0 …, entries: …". Magnus reads mem0.
5. Corrections ("no, I had the shake after the whey") → `edit`/`rm` immediately and re-summarise.

## Guidance over the day (no extra pings unless he asks)
- **Light-carb dinners (his preference, 2026-10-12).** Put rice and most roti at breakfast and lunch. Dinner is protein + sabzi + Costco salad kit
  + at most 1 roti (still with something wet). If he asks "carbs turn to fat at night?": no, total intake over days decides fat gain. Say so
  briefly, then honour the preference anyway. Exception: on evening-gym days, a few carbs at dinner help recovery.
- **A light dinner can leave him hungry by midnight** (2026-10-12: 1.5 bowls of salted peanuts at 00:09). Pre-empt it: a bigger sabzi/salad bowl
  or a katori of dal at dinner, or plan a small late snack (about 25 g peanuts, makhana, cucumber with chaat masala). Food eaten after
  midnight but before sleep counts toward the previous day (move the entry's `day`).
- **Don't overshoot the other way (2026-10-14).** Tue 13 dinner (3 drumsticks ~225 g meat + dal + ~3 cups salad kit with dressing), plus whey in dahi at 20:34, came to ~100 g fat for the day, and he still felt full the next morning. Cap dinner at ~120-150 g meat (2 drumsticks), half the kit dressing, and no whey on top of a meat dinner. If he wakes up full, don't push a big breakfast: start light and let lunch carry the load.
- **Filling light-carb dinner = protein >= 40 g + volume.** A dal-only dinner (6-10 g protein) is what ends in a late bowl of peanuts;
  a meat/paneer/egg main + 1 katori dal + 2-3 cups salad kit (+ whey in dahi later) keeps him full. Combos, a planned-late-snack list and the
  sourced "carbs at night" answer are in wiki `concepts/indian-home-meal-rules.md` (section "Filling light-carb dinners"). Check sat fat
  when the main is chicken curry or paneer (skinless, light oil).
- **Morning "what am I eating?"**: answer with today's planned breakfast, a 3-line recipe, and the macro payoff. Fit it to the day's logistics
  (e.g. ready before an 8:20 school run). Then list the rest of the day in one compact list. No re-asking.
- **Gym days:** about 25–40 g protein in the 2 h before or after training. Suggest the session time based on
  when he last ate (2–3 h after a meal is ideal).
- **By ~3 PM** he should be at ≥50% protein and have had ≥1 veg serving. If not, steer lunch/snack.
- **Evening:** close the biggest gap with real food first, then whey/shake. Skip bedtime whey on
  big-chicken days. Before bed, if veg/fruit is 0, suggest fruit or a quick salad rather than nothing.
- **Explain the tradeoff** when he picks convenience food: bars and shakes give protein but no veg,
  micronutrients or fibre variety (Quest = added fibre plus sweeteners and sat fat); bakery
  puffs and samosas are mostly refined flour and fat; high protein with no veg hurts gut and heart health and leaves him hungry.

## Realistic volume (Sumeet, 2026-10-11: "crazy volume for someone my size")
- A plan he can eat beats a plan that ticks every box. One normal plate per meal: about 120 g meat or paneer, 1 katori sabzi or dal,
  2 roti (or roti + a little rice), and at most one side. Don't stack salad + dal + dahi + rice + roti + fruit in one sitting.
- Close the protein gap first, then veg. Accept small misses on carbs, kcal and fruit late in the day rather than forcing food.
- Spread veg/fruit across the WHOLE day: fruit ON ITS OWN mid-morning (~11 AM), as a fruit chaat in the afternoon, or cut after lunch; veg via the sabzi plus a bowl of Costco salad kit (never kachumber: the household doesn't make or eat it, Sumeet 2026-10-13). Log a kit as ~2 cups: 170 kcal P3 C12 F12 sat1.5 fib4 Na230 veg1.5 (2026-10-12 entry). Flag this in the morning, not at 7 PM.
- When he's short late in the day, use dense options (a shake, whey in dahi) instead of extra plates.

## His food rules (hard)
- **Never Greek yogurt** (hates it). Plain dahi (Astro 3%) with whey is fine.
- Roti always goes with something **wet** (dal, sabzi with gravy, curry). Dry boiled eggs are a standalone snack only.
- Chai goes with a SOLID savoury snack only (paneer cubes, roasted chana, an omelette, pakoras, a protein bar). No second drink and **NEVER fruit with chai** (2026-10-11).
- Every suggestion must pass the test "would an Indian home actually eat this, at this time, in this pairing?" Read wiki `concepts/indian-home-meal-rules.md` before suggesting meals.
- Chronic hives: don't suggest new supplements casually. Supplements must be **NSF Certified for Sport** (labels are distrusted: use personal-shopper `cert_lookup.py`).
- Don't infer stock from photos ("I have plenty").

## Body data: Withings (LIVE since 2026-10-11)
- His **Withings Body Smart** scale (Pebbleway appliance 821e5fd4) syncs into the `body` table automatically:
  weight, fat %, fat mass, fat-free mass, muscle, bone, body water, visceral fat index, BMR (kcal) and heart rate.
  `$N body latest` shows the newest values. Use THESE, not memory, for any weight/body-comp question. Look at the 7-day trend
  rather than a single day. Daily swings of ±0.7–1 kg are normal. His usual cause is **food still in his system after a big dinner the night before** (he said so 2026-10-11 about an 81.8 reading). Water, salt and creatine also play a part. Don't call a single high reading a gain.
- Sync: `scripts/withings_sync.py sync [--days N]` | `status` | `auth-url`. Cron **ba0504411ee2** runs at 09:30 and 21:30
  (no_agent; script `~/.hermes/scripts/withings_sync_cron.sh`). It is silent on success, retries once, and alerts only on failure.
- Auth: his Withings login is **Sign in with Apple**, so never try to log in as him. The API app is registered under a
  SEPARATE dev account (a "+withingsdev" alias of his Proton address, see the 1Password item; emailed 8-digit login code, read via himalaya `-a proton`).
  1Password: "Withings Developer App (Mankoo Household Health Sync)". Callback
  `https://mcp.pebble.mankoo.ca/withings/callback` = Traefik `/opt/traefik/dynamic/withings-callback.yml` (PathPrefix
  `/withings/`, priority 100, does not touch the MCP router) → systemd --user `withings-callback` (127.0.0.1:3410,
  `~/.hermes/scripts/withings_callback.py`). It swaps the code for tokens instantly, because codes expire in ~30 s.
- Tokens: `~/.hermes/secrets/withings_tokens.json` (0600). Access lasts 3 h. The refresh token **rotates on every refresh**
  (the script writes it back) and lasts about 1 year. If refresh fails, send him a fresh `auth-url` link (one tap: Continue with Apple → Allow).
- Pitfalls hit during setup:
  - The dev-portal login code is 8 digits, not 6.
  - The app secret appears ONCE; it was captured by hooking `navigator.clipboard.writeText` and clicking the page's Copy button, never printed.
  - Before he finishes consent, `ls withings_tokens.json` / callback log may be empty. Withings can take a minute, so poll rather than declare failure.
- **Apple Health itself is not reachable** (HealthKit is iPhone-only; no Mac/iCloud API). If he ever wants steps or active
  energy, the route is an iOS Shortcut automation POSTing JSON to a VPS endpoint. Withings covers body composition.

## Data sources for the food table
- Generic foods: Health Canada **Canadian Nutrient File** API. Nutrients come from `nutrientamount/?id=<code>&type=json`;
  ids 208 kcal, 203 protein, 205 carbs, 204 fat, 606 sat fat, 291 fibre, 269 sugar, 307 sodium.
  Food list: `food/?lang=en&type=json`. Seed list: `scripts/seed_foods.json` (each row's `source` holds the code).
- Products: the label first, then Open Food Facts. Household dish estimates are in wiki `concepts/household-dish-protein.md`.

## Pitfalls
- **Sumeet takes chai and coffee WITHOUT sugar (2026-10-13).** The `chai` row was re-based to unsweetened (34 kcal,
  sugar 3.3 g of milk lactose). `seed_foods.json` still has the 1-tsp-sugar version, so re-apply after a reseed. Never
  assume sugar in his drinks; log Mummy's/Priyanka's chai the same way.
- **Current whey = `on_isolate_scoop`** (Optimum Nutrition Gold Standard 100% Isolate, Rich Vanilla; official panel per 30 g scoop:
  100 kcal, P25, C1, sugar1, F0, sat0, Na80). Use it for "a scoop of whey" by default. `whey_scoop` (Revolution Nutrition, 28 g P) is the
  OLD tub. His dahi is `astro_original` (Astro Original 3.3%: 3.5 g sat fat per 100 g). Whey in water costs 0 sat fat; in dahi, about 4 g per 120 g.
- **Home cooking ≠ CNF generic rows** (recalibrated 2026-10-12 after he asked "Why are we over. I followed the exact plan"):
  CNF `roti` (7250) and `paratha` (7251) assume added fat (3.3 g and 5.8 g sat per 100 g), which overstated his day by about 10 g sat fat.
  The DB now holds **home** values: phulka 35 g with no fat (P3.2, F0.6, sat0.1, Na21 per roti); paratha 80 g cooked in 1 tsp canola
  (P7.3, F6.4, sat0.6). Ghee is logged separately (`ghee` tsp). `seed_foods.json` still carries the CNF numbers, so re-apply after a reseed.
- **Plan against EVERY target before suggesting it**, not just protein. Simulate in a scratch DB copy
  (`cp nutrition.db /tmp/sim.db; NUTRITION_DB=/tmp/sim.db … log …; day today`). If a target can't be met, say so up front with a swap.
  Never present a known overage as a minor "tradeoff".
- Raw vs cooked weight: CNF meat rows are **cooked, meat only**. If he says "200 g chicken" he means cooked
  pieces on his plate. Bone-in drumsticks are about 70% edible meat.
- `egg` is per large egg (50 g); `egg_omelette` row includes cooking fat (higher sodium).
- `--json` on any command is available for scripts. Exit code is non-zero on unknown food/unit/id,
  and it suggests the closest keys.
- The DB lives outside the repo (personal data). Never commit it.
