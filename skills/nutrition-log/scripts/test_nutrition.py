#!/usr/bin/env python3
"""Tests for nutrition.py. Uses a temp DB via NUTRITION_DB; stdlib unittest."""
import json
import os
import tempfile
import unittest
from datetime import timedelta
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
        sumeet_tgts1 = c.execute(
            "SELECT COUNT(*) FROM targets WHERE person='sumeet'").fetchone()[0]
        ver = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        c.close()
        self.assertEqual(ver, "2")
        self.assertGreater(foods1, 0)
        self.assertEqual(sumeet_tgts1, len(nutrition.SEED_TARGETS))
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
        self.cli(["log", "egg", "1", "egg", "--force"])  # 2nd is a dup; force it
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
        # no water target: logging water must not create a scored status
        self.assertNotIn("water_ml", bykey)

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
        v = c.execute(
            "SELECT value FROM targets WHERE person='sumeet' AND key='protein'"
        ).fetchone()[0]
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


def _run_json(cli, argv):
    """Run a CLI command capturing stdout, parse the trailing JSON line."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli(argv)
    out = buf.getvalue()
    return rc, json.loads(out.strip().splitlines()[-1]) if out.strip() else None


def _run_capture(cli, argv):
    """Run a CLI command capturing stdout+stderr, return (rc, stdout, stderr)."""
    import io
    import contextlib
    ob, eb = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(ob), contextlib.redirect_stderr(eb):
        rc = cli(argv)
    return rc, ob.getvalue(), eb.getvalue()


class MigrationTest(unittest.TestCase):
    """v1 -> v2 migration on a DB built with the OLD schema."""

    V1_SCHEMA = """
    CREATE TABLE foods(id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL, aliases TEXT DEFAULT '',
      basis TEXT NOT NULL CHECK(basis IN ('100g','serving')), serving_g REAL,
      unit_name TEXT, kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL,
      satfat_g REAL, fibre_g REAL, sugar_g REAL, sodium_mg REAL,
      veg_servings REAL DEFAULT 0, fruit_servings REAL DEFAULT 0,
      source TEXT, notes TEXT, updated_at TEXT);
    CREATE TABLE entries(id INTEGER PRIMARY KEY, eaten_at TEXT NOT NULL,
      day TEXT NOT NULL, meal TEXT, food_id INTEGER REFERENCES foods(id),
      description TEXT NOT NULL, qty REAL NOT NULL, qty_unit TEXT NOT NULL,
      grams REAL, kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL,
      satfat_g REAL, fibre_g REAL, sugar_g REAL, sodium_mg REAL,
      veg_servings REAL, fruit_servings REAL, confidence TEXT DEFAULT 'medium',
      source TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
    CREATE INDEX idx_entries_day ON entries(day);
    CREATE TABLE water(id INTEGER PRIMARY KEY, day TEXT, ml REAL, at TEXT);
    CREATE TABLE targets(key TEXT PRIMARY KEY, value REAL,
      kind TEXT CHECK(kind IN ('min','max','range_lo','range_hi')),
      unit TEXT, note TEXT);
    CREATE TABLE body(id INTEGER PRIMARY KEY, day TEXT, metric TEXT, value REAL,
      source TEXT, at TEXT, UNIQUE(day,metric,source));
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    """

    def setUp(self):
        import sqlite3
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "nutrition.db")
        c = sqlite3.connect(self.db)
        c.executescript(self.V1_SCHEMA)
        c.execute("INSERT INTO foods(key,name,basis,protein_g,kcal) "
                  "VALUES ('chicken_breast','Chicken','100g',31.0,165)")
        c.execute(
            "INSERT INTO entries(eaten_at,day,meal,food_id,description,qty,"
            "qty_unit,grams,protein_g,kcal,created_at) VALUES "
            "('2026-10-01T12:00:00','2026-10-01','lunch',1,'Chicken',200,'g',"
            "200,62.0,330,'2026-10-01T12:00:00')")
        c.execute("INSERT INTO targets(key,value,kind,unit,note) "
                  "VALUES ('protein',140,'min','g',NULL)")
        c.execute("INSERT INTO targets(key,value,kind,unit,note) "
                  "VALUES ('kcal_lo',2300,'range_lo','kcal','x')")
        c.execute("INSERT INTO body(day,metric,value,source,at) VALUES "
                  "('2026-10-01','weight_kg',80.2,'withings','2026-10-01T07:00')")
        c.execute("INSERT INTO water(day,ml,at) VALUES "
                  "('2026-10-01',500,'2026-10-01T09:00')")
        c.execute("INSERT INTO meta(key,value) VALUES ('schema_version','1')")
        c.commit()
        c.close()
        os.environ["NUTRITION_DB"] = self.db

    def tearDown(self):
        os.environ.pop("NUTRITION_DB", None)

    def test_migration_seeds_child_targets_keeps_sumeets(self):
        """Kids get their seeded targets on migration; Sumeet keeps exactly his migrated
        rows (not re-seeded); priyanka gets none; a re-run adds nothing."""
        c = nutrition.connect()
        try:
            n = {r[0]: r[1] for r in c.execute(
                "SELECT person, COUNT(*) FROM targets GROUP BY person")}
            self.assertEqual(n.get("sumeet"), 2)  # the 2 v1 rows only
            self.assertGreater(n.get("tegh", 0), 0)
            self.assertGreater(n.get("kirat", 0), 0)
            self.assertNotIn("priyanka", n)
            self.assertIsNone(c.execute(
                "SELECT 1 FROM targets WHERE person IN ('tegh','kirat') AND key LIKE 'kcal%'"
            ).fetchone())  # never a calorie target for a child
        finally:
            c.close()
        c = nutrition.connect()
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM targets").fetchone()[0],
                             sum(n.values()))
        finally:
            c.close()

    def test_migration_preserves_and_assigns(self):
        c = nutrition.connect()  # triggers migration
        try:
            self.assertEqual(
                c.execute("SELECT value FROM meta WHERE key='schema_version'"
                          ).fetchone()[0], "2")
            # entry preserved, assigned to sumeet, defaults applied
            e = c.execute("SELECT * FROM entries").fetchone()
            self.assertEqual(e["person"], "sumeet")
            self.assertAlmostEqual(e["protein_g"], 62.0)
            self.assertEqual(e["status"], "eaten")
            self.assertAlmostEqual(e["eaten_fraction"], 1.0)
            self.assertIsNone(e["iron_mg"])  # unknown, not zero
            # targets moved to sumeet
            t = c.execute("SELECT person,value FROM targets WHERE key='protein'"
                          ).fetchone()
            self.assertEqual(t["person"], "sumeet")
            self.assertAlmostEqual(t["value"], 140.0)
            # body + water carried a person
            self.assertEqual(
                c.execute("SELECT person FROM body").fetchone()["person"], "sumeet")
            self.assertEqual(
                c.execute("SELECT person FROM water").fetchone()["person"], "sumeet")
            # people seeded
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM people").fetchone()[0], 4)
            self.assertEqual(
                c.execute("SELECT kind FROM people WHERE key='tegh'").fetchone()[0],
                "child")
        finally:
            c.close()

    def test_migration_idempotent(self):
        c = nutrition.connect()
        c.close()
        c = nutrition.connect()  # re-run migration
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 1)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM targets WHERE person='sumeet'").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM people").fetchone()[0], 4)
            self.assertEqual(
                c.execute("SELECT value FROM meta WHERE key='schema_version'"
                          ).fetchone()[0], "2")
        finally:
            c.close()


GOOD_AUTH = "test-" + "client-key"  # fake, test-only


class HouseholdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "nutrition.db")
        os.environ["NUTRITION_DB"] = self.db
        os.environ.pop("NUTRITION_PERSON", None)
        os.environ.pop("NUTRITION_AGENT", None)
        self.cli(["init"])

    def tearDown(self):
        os.environ.pop("NUTRITION_DB", None)
        os.environ.pop("NUTRITION_PERSON", None)
        os.environ.pop("NUTRITION_AGENT", None)

    def cli(self, argv):
        return nutrition.main(argv)

    def conn(self):
        return nutrition.connect()

    def today(self):
        return nutrition.now_dt().date().isoformat()

    # ----- person filtering ----- #
    def test_person_filtering(self):
        self.cli(["log", "chicken_breast", "200", "g"])            # sumeet
        self.cli(["log", "egg", "1", "egg", "--person", "tegh"])   # tegh
        rc, obj = _run_json(self.cli, ["day", "today", "--json"])  # sumeet default
        self.assertEqual(len(obj["entries"]), 1)
        self.assertEqual(obj["entries"][0]["person"], "sumeet")
        rc, obj = _run_json(self.cli, ["day", "today", "--person", "tegh", "--json"])
        self.assertEqual(len(obj["entries"]), 1)
        self.assertEqual(obj["entries"][0]["person"], "tegh")

    def test_unknown_person_errors(self):
        rc, out, err = _run_capture(self.cli, ["day", "today", "--person", "nobody"])
        self.assertEqual(rc, 1)
        self.assertIn("unknown person", err)

    def test_person_env_default(self):
        os.environ["NUTRITION_PERSON"] = "tegh"
        try:
            self.cli(["log", "egg", "1", "egg"])
        finally:
            os.environ.pop("NUTRITION_PERSON", None)
        c = self.conn()
        p = c.execute("SELECT person FROM entries").fetchone()[0]
        c.close()
        self.assertEqual(p, "tegh")

    def test_child_output_hides_adult_nutrients(self):
        self.cli(["log", "roti", "1", "--person", "tegh"])
        rc, out, err = _run_capture(
            self.cli, ["day", "today", "--person", "tegh"])
        low = out.lower()
        self.assertNotIn("kcal", low)
        self.assertNotIn("carb", low)
        self.assertNotIn("sugar", low)
        self.assertNotIn("sodium", low)
        self.assertNotIn("fat", low)   # also catches 'satfat'
        # but it does show protein / iron / calcium / fibre
        self.assertIn("protein", low)
        self.assertIn("iron", low)
        self.assertIn("calcium", low)

    def test_child_summary_and_week_hide_kcal(self):
        self.cli(["log", "roti", "1", "--person", "tegh"])
        for cmd in (["summary", "--person", "tegh"], ["week", "--person", "tegh"]):
            rc, out, err = _run_capture(self.cli, cmd)
            self.assertNotIn("kcal", out.lower(), f"{cmd} leaked kcal")

    def test_adult_output_still_has_kcal(self):
        self.cli(["log", "chicken_breast", "200", "g"])
        rc, out, err = _run_capture(self.cli, ["day", "today"])
        self.assertIn("kcal", out.lower())

    # ----- dedup ----- #
    def test_dedup_same_food_within_3h(self):
        self.cli(["log", "egg", "1", "egg", "--at", "08:00"])
        rc, out, err = _run_capture(
            self.cli, ["log", "egg", "1", "egg", "--at", "09:00"])
        self.assertEqual(rc, 3)
        self.assertIn("POSSIBLE DUPLICATE", out)
        c = self.conn()
        n = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        c.close()
        self.assertEqual(n, 1)  # nothing written

    def test_dedup_force_writes(self):
        self.cli(["log", "egg", "1", "egg", "--at", "08:00"])
        rc = self.cli(["log", "egg", "1", "egg", "--at", "09:00", "--force"])
        self.assertEqual(rc, 0)
        c = self.conn()
        rows = c.execute("SELECT notes FROM entries ORDER BY id").fetchall()
        c.close()
        self.assertEqual(len(rows), 2)
        self.assertIn("confirmed not a duplicate", rows[1]["notes"] or "")

    def test_dedup_different_person_no_dup(self):
        self.cli(["log", "egg", "1", "egg", "--at", "08:00"])
        rc = self.cli(["log", "egg", "1", "egg", "--at", "08:30", "--person", "tegh"])
        self.assertEqual(rc, 0)

    def test_dedup_outside_3h_no_dup(self):
        self.cli(["log", "egg", "1", "egg", "--at", "08:00"])
        rc = self.cli(["log", "egg", "1", "egg", "--at", "13:00"])  # 5h later
        self.assertEqual(rc, 0)

    def test_dedup_similar_desc_different_reporter(self):
        self.cli(["log-custom", "--desc", "butter chicken from restaurant",
                  "--protein", "30", "--at", "19:00", "--reported-by", "sumeet"])
        rc, out, err = _run_capture(
            self.cli, ["log-custom", "--desc", "restaurant butter chicken",
                       "--protein", "30", "--at", "19:30",
                       "--reported-by", "priyanka"])
        self.assertEqual(rc, 3)
        self.assertIn("POSSIBLE DUPLICATE", out)

    def test_dedup_json(self):
        self.cli(["log", "egg", "1", "egg", "--at", "08:00"])
        rc, obj = _run_json(
            self.cli, ["log", "egg", "1", "egg", "--at", "09:00", "--json"])
        self.assertEqual(rc, 3)
        self.assertTrue(obj["duplicate"])
        self.assertEqual(len(obj["matches"]), 1)

    # ----- packed / eaten ----- #
    def test_packed_then_eaten_fraction(self):
        self.cli(["log", "paratha", "1", "--person", "tegh", "--packed"])
        c = self.conn()
        eid = c.execute("SELECT id FROM entries").fetchone()[0]
        full = nutrition.day_totals(c, self.today(), "tegh")["protein_g"]
        c.close()
        self.assertGreater(full, 0)
        self.cli(["eaten", str(eid), "--fraction", "0.5"])
        c = self.conn()
        row = c.execute("SELECT status, eaten_fraction FROM entries").fetchone()
        half = nutrition.day_totals(c, self.today(), "tegh")["protein_g"]
        c.close()
        self.assertEqual(row["status"], "partial")
        self.assertAlmostEqual(row["eaten_fraction"], 0.5)
        self.assertAlmostEqual(half, full / 2.0, places=4)

    def test_eaten_none_zeroes(self):
        self.cli(["log", "paratha", "1", "--person", "tegh", "--packed"])
        c = self.conn()
        eid = c.execute("SELECT id FROM entries").fetchone()[0]
        c.close()
        self.cli(["eaten", str(eid), "--none"])
        c = self.conn()
        row = c.execute("SELECT status, eaten_fraction FROM entries").fetchone()
        tot = nutrition.day_totals(c, self.today(), "tegh")["protein_g"]
        c.close()
        self.assertEqual(row["status"], "returned")
        self.assertAlmostEqual(row["eaten_fraction"], 0.0)
        self.assertAlmostEqual(tot, 0.0)

    def test_packed_counts_until_adjusted(self):
        # a packed row counts at 1.0 until eaten adjusts it
        self.cli(["log", "paratha", "1", "--person", "tegh"])
        c = self.conn()
        eaten_tot = nutrition.day_totals(c, self.today(), "tegh")["protein_g"]
        c.close()
        self.cli(["log", "paratha", "1", "--person", "tegh", "--packed",
                  "--at", "18:00", "--force"])
        c = self.conn()
        packed_tot = nutrition.day_totals(c, self.today(), "tegh")["protein_g"]
        c.close()
        self.assertAlmostEqual(packed_tot, eaten_tot * 2, places=4)

    # ----- unknown minerals ----- #
    def test_unknown_minerals_not_counted_zero(self):
        # whey_scoop has NULL iron/calcium (no CNF code)
        self.cli(["log", "whey_scoop", "1", "scoop", "--person", "tegh"])
        c = self.conn()
        totals = nutrition.day_totals(c, self.today(), "tegh")
        c.close()
        self.assertEqual(totals["_unknown"]["iron_mg"], 1)
        self.assertEqual(totals["iron_mg"], 0.0)  # not silently counted
        # child totals line surfaces the unknown count, not a bare 0
        rc, out, err = _run_capture(self.cli, ["day", "today", "--person", "tegh"])
        self.assertIn("unknown", out.lower())

    def test_known_minerals_counted(self):
        self.cli(["log", "spinach", "100", "g"])  # spinach has iron
        c = self.conn()
        totals = nutrition.day_totals(c, self.today(), "sumeet")
        c.close()
        self.assertEqual(totals["_unknown"]["iron_mg"], 0)
        self.assertGreater(totals["iron_mg"], 0)

    # ----- gaps ----- #
    def test_gaps_flags_repeated_miss(self):
        today = nutrition.now_dt().date()
        d0 = today.isoformat()
        d1 = (today - timedelta(days=1)).isoformat()
        # log a tiny amount (far below iron target) on two days for tegh
        self.cli(["log", "egg", "1", "egg", "--person", "tegh", "--at", f"{d0} 08:00"])
        self.cli(["log", "egg", "1", "egg", "--person", "tegh", "--at", f"{d1} 08:00"])
        rc, obj = _run_json(self.cli, ["gaps", "--days", "3", "--person", "tegh",
                                       "--json"])
        tegh = [p for p in obj["people"] if p["person"] == "tegh"][0]
        gnames = [g["nutrient"] for g in tegh["gaps"]]
        self.assertIn("iron", gnames)
        self.assertFalse(tegh["on_track"])

    def test_gaps_ignores_single_bad_day(self):
        today = nutrition.now_dt().date()
        d0 = today.isoformat()
        # only one day of (bad) data -> not a repeated miss
        self.cli(["log", "egg", "1", "egg", "--person", "tegh", "--at", f"{d0} 08:00"])
        rc, obj = _run_json(self.cli, ["gaps", "--days", "3", "--person", "tegh",
                                       "--json"])
        tegh = [p for p in obj["people"] if p["person"] == "tegh"][0]
        self.assertTrue(tegh["on_track"])
        self.assertEqual(tegh["gaps"], [])

    # ----- people-day ----- #
    def test_people_day(self):
        self.cli(["log", "chicken_breast", "200", "g"])
        self.cli(["log", "egg", "1", "egg", "--person", "tegh"])
        rc, obj = _run_json(self.cli, ["people-day", "today", "--json"])
        persons = {p["person"] for p in obj["people"]}
        self.assertEqual(persons, {"sumeet", "tegh"})

    # ----- targets per person ----- #
    def test_priyanka_no_targets(self):
        rc, obj = _run_json(self.cli, ["targets", "--person", "priyanka", "--json"])
        self.assertEqual(obj["targets"], {})

    def test_child_has_no_kcal_target(self):
        c = self.conn()
        rows = c.execute(
            "SELECT key FROM targets WHERE person='tegh'").fetchall()
        c.close()
        keys = {r["key"] for r in rows}
        self.assertNotIn("kcal_lo", keys)
        self.assertNotIn("kcal_hi", keys)
        self.assertIn("iron", keys)
        self.assertIn("calcium", keys)

    def test_kirat_milk_target(self):
        c = self.conn()
        r = c.execute(
            "SELECT value, kind FROM targets WHERE person='kirat' AND key='milk_ml'"
        ).fetchone()
        c.close()
        self.assertAlmostEqual(r["value"], 500.0)
        self.assertEqual(r["kind"], "max")


class ServerTest(unittest.TestCase):
    def setUp(self):
        import socket
        import threading
        import importlib
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "nutrition.db")
        self.tokens = os.path.join(self.tmp, "tokens.json")
        with open(self.tokens, "w") as fh:
            json.dump({GOOD_AUTH: "shankar"}, fh)
        os.chmod(self.tokens, 0o600)
        os.environ["NUTRITION_DB"] = self.db
        os.environ["NUTRITION_TOKENS"] = self.tokens
        nutrition.main(["init"])

        # pick an ephemeral port
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        os.environ["NUTRITION_BIND"] = "127.0.0.1"
        os.environ["NUTRITION_PORT"] = str(self.port)

        import nutrition_server
        importlib.reload(nutrition_server)
        self.srv_mod = nutrition_server
        from http.server import ThreadingHTTPServer
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", self.port), nutrition_server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for k in ("NUTRITION_DB", "NUTRITION_TOKENS", "NUTRITION_BIND",
                  "NUTRITION_PORT", "NUTRITION_ALLOW_IPS"):
            os.environ.pop(k, None)

    def _post(self, argv, auth=GOOD_AUTH):
        import urllib.request
        import urllib.error
        req = urllib.request.Request(
            self.base + "/run",
            data=json.dumps({"argv": argv}).encode(),
            method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + auth} if auth
            else {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_health(self):
        import urllib.request
        with urllib.request.urlopen(self.base + "/health", timeout=10) as r:
            obj = json.loads(r.read())
        self.assertTrue(obj["ok"])
        self.assertEqual(obj["schema"], "2")

    def test_bad_token_401(self):
        code, obj = self._post(["day", "today", "--person", "tegh"], auth="x-invalid")
        self.assertEqual(code, 401)

    def test_missing_person_on_log_400(self):
        code, obj = self._post(["log", "egg", "1", "egg"])
        self.assertEqual(code, 400)
        self.assertIn("person", obj["error"])

    def test_disallowed_subcommand(self):
        code, obj = self._post(["init"])
        self.assertEqual(code, 403)

    def test_disallowed_food_rm(self):
        code, obj = self._post(["food", "rm", "egg"])
        self.assertEqual(code, 403)

    def test_logged_by_ignored(self):
        code, obj = self._post(
            ["log", "egg", "1", "egg", "--person", "tegh",
             "--logged-by", "evil", "--json"])
        self.assertEqual(code, 200)
        self.assertEqual(obj["exit"], 0)
        c = nutrition.connect()
        lb = c.execute("SELECT logged_by FROM entries").fetchone()[0]
        c.close()
        self.assertEqual(lb, "shankar")

    def test_remote_duplicate_exit_3(self):
        c1, o1 = self._post(["log", "egg", "1", "egg", "--person", "tegh",
                             "--at", "08:00"])
        self.assertEqual(o1["exit"], 0)
        c2, o2 = self._post(["log", "egg", "1", "egg", "--person", "tegh",
                             "--at", "09:00"])
        self.assertEqual(c2, 200)
        self.assertEqual(o2["exit"], 3)
        self.assertIn("POSSIBLE DUPLICATE", o2["stdout"])

    def test_targets_set_blocked_for_adult(self):
        # sumeet is an adult who isn't priyanka -> blocked
        code, obj = self._post(["targets", "set", "protein", "150",
                                "--person", "sumeet"])
        self.assertEqual(code, 403)

    def test_targets_set_ok_for_child(self):
        code, obj = self._post(["targets", "set", "protein", "20",
                                "--person", "tegh", "--json"])
        self.assertEqual(code, 200)
        self.assertEqual(obj["exit"], 0)

    def test_targets_set_ok_for_priyanka(self):
        code, obj = self._post(["targets", "set", "protein", "110",
                                "--person", "priyanka", "--kind", "min", "--json"])
        self.assertEqual(code, 200)
        self.assertEqual(obj["exit"], 0)


if __name__ == "__main__":
    unittest.main()
