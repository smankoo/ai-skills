"""Add seed foods that are MISSING from a nutrition DB, without touching existing (calibrated) rows.
Usage: NUTRITION_DB=<db> python3 seed_missing.py [--dry-run]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nutrition

dry = "--dry-run" in sys.argv
conn = nutrition.connect()  # also runs the schema migration
have = {r[0] for r in conn.execute("SELECT key FROM foods")}
seed = json.loads((Path(__file__).resolve().parent / "seed_foods.json").read_text())
added = []
for food in seed:
    if food["key"] in have:
        continue
    added.append(food["key"])
    if not dry:
        nutrition.upsert_food(conn, {k: food.get(k) for k in nutrition.FOOD_COLS if k in food})
# densities for drinks: fill only where still NULL
for food in seed:
    d = food.get("density_g_ml")
    if d and not dry:
        conn.execute("UPDATE foods SET density_g_ml=? WHERE key=? AND density_g_ml IS NULL", (d, food["key"]))
conn.commit()
print(("would add: " if dry else "added: ") + (", ".join(added) or "nothing"))
