#!/usr/bin/env python3
"""Tests for nutrition.py. Uses a temp DB via NUTRITION_DB; stdlib unittest."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import nutrition


class NutritionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "nutrition.db")
        os.environ["NUTRITION_DB"] = self.db
        self.cli(["init"])

    def tearDown(self):
        os.environ.pop("NUTRITION_DB", None)

    # helper: run a CLI command, return exit code
    def cli(self, argv):
        return nutrition.main(argv)

    def conn(self):
        return nutrition.connect()

    def totals(self, day):
        c = self.conn()
        try:
            return nutrition.day_totals(c, day)
        finally:
            c.close()

    def today(self):
        return nutrition.now_dt().date().isoformat()

    # --------------------------------------------------------------------- #
    def test_init_idempotent(self):
        c = self.conn()
        foods1 = c.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
        tgts1 = c.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
        ver = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        c.close()
        self.assertEqual(ver, "1")
        self.assertGreater(foods1, 0)
        self.assertEqual(tgts1, len(nutrition.SEED_TARGETS))
        # re-run
        self.assertEqual(self.cli(["init"]), 0)
        c = self.conn()
        foods2 = c.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
        tgts2 = c.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
        entries = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        c.close()
        self.assertEqual(foods1, foods2)
        self.assertEqual(tgts1, tgts2)
        self.assertEqual(entries, 0)

    def test_log_by_grams_100g_food(self):
        # chicken_breast: 31.02 g protein / 100 g, 165 kcal / 100 g
        self.assertEqual(self.cli(["log", "chicken_breast", "200", "g"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 62.04, places=2)
        self.assertAlmostEqual(t["kcal"], 330.0, places=2)
        # grams snapshot stored
        c = self.conn()
        r = c.execute("SELECT * FROM entries").fetchone()
        c.close()
        self.assertAlmostEqual(r["grams"], 200.0)
        self.assertEqual(r["qty_unit"], "g")

    def test_log_by_unit_eggs(self):
        # egg basis 100g, serving_g 50, 11.8 g protein /100g -> per egg 5.9 g
        self.assertEqual(self.cli(["log", "egg", "2", "eggs"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 11.8, places=2)  # 2*50g = 100g
        self.assertAlmostEqual(t["kcal"], 145.0, places=2)
        c = self.conn()
        r = c.execute("SELECT * FROM entries").fetchone()
        c.close()
        self.assertAlmostEqual(r["grams"], 100.0)
        self.assertEqual(r["qty_unit"], "egg")

    def test_log_by_serving_scoop(self):
        # whey_scoop basis serving, 28 g protein / serving
        self.assertEqual(self.cli(["log", "whey_scoop", "1", "scoop"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 28.0, places=2)
        self.assertAlmostEqual(t["kcal"], 134.0, places=2)

    def test_plural_unit_tolerance(self):
        # 'rotis' plural of unit 'roti'; 'scoops' plural of 'scoop'
        self.assertEqual(self.cli(["log", "roti", "2", "rotis"]), 0)
        self.assertEqual(self.cli(["log", "whey_scoop", "2", "scoops"]), 0)
        c = self.conn()
        rows = c.execute("SELECT * FROM entries ORDER BY id").fetchall()
        c.close()
        # roti: 40g each, 2 rotis = 80g, protein 7.85/100g -> 6.28g
        self.assertAlmostEqual(rows[0]["protein_g"], 7.85 * 0.8, places=2)
        self.assertEqual(rows[0]["qty_unit"], "roti")
        self.assertAlmostEqual(rows[1]["protein_g"], 56.0, places=2)

    def test_log_serving_x_alias(self):
        self.assertEqual(self.cli(["log", "premier_shake", "1", "x"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 30.0, places=2)

    def test_log_default_unit(self):
        # whey_scoop basis serving -> qty with no unit means servings
        self.assertEqual(self.cli(["log", "whey_scoop", "2"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 56.0, places=2)
        # chicken_breast 100g no unit_name -> grams
        self.assertEqual(self.cli(["log", "chicken_breast", "100"]), 0)
        c = self.conn()
        r = c.execute("SELECT * FROM entries WHERE food_id=(SELECT id FROM foods WHERE key='chicken_breast')").fetchone()
        c.close()
        self.assertEqual(r["qty_unit"], "g")

    def test_log_custom(self):
        self.assertEqual(self.cli(
            ["log-custom", "--desc", "restaurant butter chicken",
             "--protein", "35", "--kcal", "650", "--meal", "dinner"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 35.0, places=2)
        self.assertAlmostEqual(t["kcal"], 650.0, places=2)
        c = self.conn()
        r = c.execute("SELECT * FROM entries").fetchone()
        c.close()
        self.assertIsNone(r["food_id"])
        self.assertEqual(r["description"], "restaurant butter chicken")

    def test_edit_recomputes(self):
        self.cli(["log", "chicken_breast", "100", "g"])
        c = self.conn()
        eid = c.execute("SELECT id FROM entries").fetchone()[0]
        c.close()
        self.assertEqual(self.cli(["edit", str(eid), "--qty", "250"]), 0)
        c = self.conn()
        r = c.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        c.close()
        self.assertAlmostEqual(r["grams"], 250.0)
        self.assertAlmostEqual(r["protein_g"], 31.02 * 2.5, places=2)
        self.assertAlmostEqual(r["kcal"], 165.0 * 2.5, places=2)

    def test_edit_unit_change_recomputes(self):
        self.cli(["log", "egg", "100", "g"])  # 100g
        c = self.conn()
        eid = c.execute("SELECT id FROM entries").fetchone()[0]
        c.close()
        # change to 3 eggs -> 150g
        self.cli(["edit", str(eid), "--qty", "3", "--unit", "eggs"])
        c = self.conn()
        r = c.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        c.close()
        self.assertAlmostEqual(r["grams"], 150.0)
        self.assertEqual(r["qty_unit"], "egg")

    def test_rm(self):
        self.cli(["log", "egg", "1", "egg"])
        self.cli(["log", "egg", "1", "egg"])
        c = self.conn()
        ids = [r[0] for r in c.execute("SELECT id FROM entries").fetchall()]
        c.close()
        self.assertEqual(self.cli(["rm", str(ids[0]), str(ids[1])]), 0)
        c = self.conn()
        n = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        c.close()
        self.assertEqual(n, 0)

    def test_rm_bad_id(self):
        self.assertEqual(self.cli(["rm", "99999"]), 1)

    def test_day_totals_and_target_status(self):
        self.cli(["log", "chicken_breast", "200", "g"])  # 62.04 P, 330 kcal
        self.cli(["log", "whey_scoop", "1", "scoop"])    # +28 P, +134 kcal
        self.cli(["water", "1000"])
        c = self.conn()
        totals = nutrition.day_totals(c, self.today())
        statuses = nutrition.target_statuses(c, totals)
        c.close()
        bykey = {s["nutrient"]: s for s in statuses}
        # protein target min 140; have ~90 -> under, need ~50
        self.assertEqual(bykey["protein"]["state"], "under")
        self.assertAlmostEqual(bykey["protein"]["total"], 90.04, places=2)
        # kcal range 2300-2600; have 464 -> below
        self.assertEqual(bykey["kcal"]["state"], "below")
        # satfat max 25; low -> ok
        self.assertEqual(bykey["satfat"]["state"], "ok")
        # water min 3000; have 1000 -> under
        self.assertEqual(bykey["water_ml"]["state"], "under")
        self.assertAlmostEqual(bykey["water_ml"]["total"], 1000.0)

    def test_target_status_max_over(self):
        c = self.conn()
        # force sodium over by logging lots of papad (1745 mg/100g)
        c.close()
        self.cli(["log", "papad", "200", "g"])  # 3490 mg sodium
        c = self.conn()
        totals = nutrition.day_totals(c, self.today())
        statuses = {s["nutrient"]: s for s in nutrition.target_statuses(c, totals)}
        c.close()
        self.assertEqual(statuses["sodium"]["state"], "over")

    def test_best_levers(self):
        self.cli(["log", "whey_scoop", "1", "scoop"])
        c = self.conn()
        totals = nutrition.day_totals(c, self.today())
        statuses = nutrition.target_statuses(c, totals)
        c.close()
        levers = nutrition.best_levers(statuses, 2)
        self.assertEqual(len(levers), 2)
        # with almost nothing logged, veg/fruit/water/fibre are all far below;
        # levers are names only
        self.assertTrue(all(isinstance(x, str) for x in levers))

    def test_unknown_food_suggests(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = self.cli(["log", "chikken", "100", "g"])
        self.assertEqual(rc, 1)
        err = buf.getvalue()
        self.assertIn("unknown food", err)
        # should suggest chicken_* keys
        self.assertIn("chicken", err)

    def test_bad_unit(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = self.cli(["log", "chicken_breast", "2", "floops"])
        self.assertEqual(rc, 1)
        self.assertIn("bad unit", buf.getvalue())

    def test_week_averages(self):
        # log known values on two days
        today = self.today()
        self.cli(["log", "chicken_breast", "100", "g", "--at", f"{today} 12:00"])
        self.cli(["log", "chicken_breast", "100", "g",
                  "--at", f"{self._yesterday()} 12:00"])
        c = self.conn()
        totals_today = nutrition.day_totals(c, today)
        c.close()
        self.assertAlmostEqual(totals_today["protein_g"], 31.02, places=2)
        # 7-day protein average: (31.02 + 31.02)/7
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.cli(["week", "--json"])
        obj = json.loads(buf.getvalue())
        self.assertAlmostEqual(obj["averages"]["protein_g"], (31.02 * 2) / 7, places=2)
        self.assertEqual(len(obj["days"]), 7)

    def test_food_find_ranking(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.cli(["food", "find", "chicken", "--json"])
        obj = json.loads(buf.getvalue())
        keys = [m["key"] for m in obj["matches"]]
        self.assertIn("chicken_breast", keys)
        self.assertIn("chicken_thigh", keys)

    def test_food_add_and_log(self):
        self.assertEqual(self.cli(
            ["food", "add", "--key", "testbar", "--name", "Test Bar",
             "--basis", "serving", "--serving-g", "50", "--unit", "bar",
             "--kcal", "200", "--protein", "20", "--carbs", "20", "--fat", "7",
             "--satfat", "2", "--fibre", "5", "--sugar", "1", "--sodium", "100"]), 0)
        self.assertEqual(self.cli(["log", "testbar", "2", "bars"]), 0)
        t = self.totals(self.today())
        self.assertAlmostEqual(t["protein_g"], 40.0, places=2)

    def test_food_rm_refused_when_referenced(self):
        self.cli(["log", "egg", "1", "egg"])
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = self.cli(["food", "rm", "egg"])
        self.assertEqual(rc, 1)
        self.assertIn("referenced", buf.getvalue())
        # with --force it works
        self.assertEqual(self.cli(["food", "rm", "egg", "--force"]), 0)

    def test_body_add_and_latest(self):
        self.cli(["body", "add", "weight_kg", "80.5", "--source", "withings",
                  "--day", "2026-10-10"])
        self.cli(["body", "add", "weight_kg", "80.1", "--source", "withings",
                  "--day", "2026-10-11"])
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.cli(["body", "latest", "weight_kg", "--json"])
        obj = json.loads(buf.getvalue())
        self.assertAlmostEqual(obj["weight_kg"]["value"], 80.1)
        self.assertEqual(obj["weight_kg"]["day"], "2026-10-11")

    def test_targets_set(self):
        self.assertEqual(self.cli(["targets", "set", "protein", "160"]), 0)
        c = self.conn()
        v = c.execute("SELECT value FROM targets WHERE key='protein'").fetchone()[0]
        c.close()
        self.assertEqual(v, 160.0)

    def test_export(self):
        self.cli(["log", "egg", "1", "egg"])
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.cli(["export", "--json"])
        rows = json.loads(buf.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Egg, whole (raw weight)")

    def test_at_hhmm(self):
        self.cli(["log", "egg", "1", "egg", "--at", "08:30"])
        c = self.conn()
        r = c.execute("SELECT * FROM entries").fetchone()
        c.close()
        self.assertEqual(r["eaten_at"][11:16], "08:30")
        self.assertEqual(r["day"], self.today())

    def _yesterday(self):
        from datetime import timedelta
        return (nutrition.now_dt().date() - timedelta(days=1)).isoformat()


if __name__ == "__main__":
    unittest.main()
