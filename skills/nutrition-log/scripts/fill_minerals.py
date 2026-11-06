#!/usr/bin/env python3
"""fill_minerals.py — backfill iron_mg and calcium_mg on foods from the CNF.

For each food whose `source` contains a Canadian Nutrient File food code
(e.g. "CNF 7250"), fetch iron (nutrient id 303) and calcium (id 301) per 100 g
and write them into foods.iron_mg / foods.calcium_mg. Values are stored in the
same basis as the rest of the food's nutrients:
  - basis '100g'    -> value per 100 g (as returned by CNF)
  - basis 'serving' -> value per serving (per-100 g * serving_g / 100)

Never invents a value: a food whose code can't be resolved (no code, HTTP
failure, or missing nutrient) is left NULL and reported.

Usage:
  fill_minerals.py --db /path/to/temp_copy.db [--dry-run]

Stdlib only. Run it against a temp copy of the DB, not the live one.
"""
import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request

CNF_URL = ("https://food-nutrition.canada.ca/api/canadian-nutrient-file/"
           "nutrientamount/?id={code}&type=json&lang=en")
IRON_ID = 303
CALCIUM_ID = 301
CODE_RE = re.compile(r"\bCNF\s*(\d+)\b", re.IGNORECASE)


def parse_code(source):
    if not source:
        return None
    m = CODE_RE.search(source)
    return m.group(1) if m else None


def fetch_minerals(code, timeout=20):
    """Return (iron_per100g, calcium_per100g); either may be None if absent."""
    url = CNF_URL.format(code=code)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.load(r)
    iron = calcium = None
    for row in data:
        nid = row.get("nutrient_name_id")
        val = row.get("nutrient_value")
        if nid == IRON_ID:
            iron = val
        elif nid == CALCIUM_ID:
            calcium = val
    return iron, calcium


def scale(per100g, basis, serving_g):
    """Convert a per-100 g value into the food's stored basis."""
    if per100g is None:
        return None
    if basis == "serving":
        if not serving_g:
            return None  # can't scale without a serving weight
        return per100g * serving_g / 100.0
    return per100g  # 100g basis


def main(argv=None):
    ap = argparse.ArgumentParser(description="backfill iron/calcium from the CNF")
    ap.add_argument("--db", required=True, help="path to a (temp copy) nutrition.db")
    ap.add_argument("--dry-run", action="store_true",
                    help="print changes without writing")
    ap.add_argument("--seed-out",
                    help="also write updated per-100g values into this seed_foods.json")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    foods = conn.execute(
        "SELECT id, key, name, basis, serving_g, source, iron_mg, calcium_mg "
        "FROM foods ORDER BY key").fetchall()

    changed, unresolved, skipped = [], [], []
    per100g_by_key = {}  # key -> {iron, calcium} per 100g, for seed update

    for f in foods:
        code = parse_code(f["source"])
        if not code:
            skipped.append((f["key"], "no CNF code in source"))
            continue
        try:
            iron100, cal100 = fetch_minerals(code)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, ValueError) as e:
            unresolved.append((f["key"], f"CNF {code}: fetch failed ({e})"))
            continue
        if iron100 is None and cal100 is None:
            unresolved.append((f["key"], f"CNF {code}: no iron/calcium in response"))
            continue

        iron = scale(iron100, f["basis"], f["serving_g"])
        cal = scale(cal100, f["basis"], f["serving_g"])
        per100g_by_key[f["key"]] = {"iron_mg": iron100, "calcium_mg": cal100}

        notes = []
        if iron is not None:
            notes.append(f"iron {iron:.3g} mg")
        if cal is not None:
            notes.append(f"calcium {cal:.3g} mg")
        basis_note = f"({f['basis']}" + (
            f", /serving {f['serving_g']}g)" if f["basis"] == "serving" else ")")
        changed.append((f["key"], f["id"], iron, cal,
                        f"CNF {code} -> " + ", ".join(notes) + " " + basis_note))

        if not args.dry_run:
            conn.execute("UPDATE foods SET iron_mg=?, calcium_mg=? WHERE id=?",
                         (iron, cal, f["id"]))

    if not args.dry_run:
        conn.commit()

    # optionally propagate per-100g values back into a seed_foods.json
    if args.seed_out and per100g_by_key:
        try:
            with open(args.seed_out) as fh:
                seed = json.load(fh)
            for food in seed:
                vals = per100g_by_key.get(food.get("key"))
                if vals:
                    food["iron_mg"] = vals["iron_mg"]
                    food["calcium_mg"] = vals["calcium_mg"]
            if not args.dry_run:
                with open(args.seed_out, "w") as fh:
                    json.dump(seed, fh, indent=1, ensure_ascii=False)
                    fh.write("\n")
        except (OSError, json.JSONDecodeError) as e:
            print(f"warning: could not update seed file {args.seed_out}: {e}",
                  file=sys.stderr)

    conn.close()

    mode = "DRY-RUN (no writes)" if args.dry_run else "WROTE"
    print(f"=== fill_minerals {mode} ===")
    print(f"foods: {len(foods)} total, {len(changed)} resolved, "
          f"{len(unresolved)} unresolved, {len(skipped)} skipped (no code)")
    if changed:
        print("\nresolved:")
        for key, _id, _ir, _ca, note in changed:
            print(f"  {key:<16} {note}")
    if unresolved:
        print("\nunresolved (left NULL):")
        for key, why in unresolved:
            print(f"  {key:<16} {why}")
    if skipped:
        print("\nskipped (no CNF code, left NULL):")
        for key, why in skipped:
            print(f"  {key:<16} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
