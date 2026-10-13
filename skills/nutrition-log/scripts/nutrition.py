#!/usr/bin/env python3
"""nutrition.py — household food + nutrient tracker (SQLite + CLI, stdlib only).

A shared tracker for the household: Sumeet and Priyanka (adults), Tegh and
Kirat (children). Two agents read and write the SAME database: "hermes" (local
CLI on this VPS) and "shankar" (a second agent on another machine via
nutrition_server.py / nutrition_client.py). Either parent may log for anyone,
through either agent.

DB: env NUTRITION_DB else ~/.hermes/data/nutrition.db (WAL mode). Schema v2 is
migrated automatically, idempotently and losslessly from v1 on connect().

Every reading/writing command takes a global --person (default env
NUTRITION_PERSON, else 'sumeet'). Writes also carry --logged-by (which agent,
default env NUTRITION_AGENT else 'hermes') and --reported-by (which human).

Common usage:
  nutrition.py init
  nutrition.py log egg 2 eggs --meal breakfast --at now
  nutrition.py log paratha 1 --person tegh --packed --reported-by priyanka
  nutrition.py eaten 42 --fraction 0.5 --note "came back half"
  nutrition.py day today --person tegh
  nutrition.py summary --person kirat
  nutrition.py gaps --days 3
  nutrition.py people-day today

Every command supports --json for compact machine output.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover - zoneinfo always present on 3.9+
    TZ = None

SCHEMA_VERSION = "2"

# Nutrient columns scaled from the food table into each entry snapshot.
FOOD_NUTRIENTS = [
    "kcal", "protein_g", "carbs_g", "fat_g", "satfat_g",
    "fibre_g", "sugar_g", "sodium_mg", "iron_mg", "calcium_mg",
    "veg_servings", "fruit_servings",
]

FOOD_COLS = [
    "key", "name", "aliases", "basis", "serving_g", "unit_name", "density_g_ml",
    "kcal", "protein_g", "carbs_g", "fat_g", "satfat_g", "fibre_g",
    "sugar_g", "sodium_mg", "iron_mg", "calcium_mg",
    "veg_servings", "fruit_servings",
    "source", "notes", "updated_at",
]

ENTRY_COLS = [
    "person", "eaten_at", "day", "meal", "food_id", "description", "qty",
    "qty_unit", "grams", "kcal", "protein_g", "carbs_g", "fat_g", "satfat_g",
    "fibre_g", "sugar_g", "sodium_mg", "iron_mg", "calcium_mg",
    "veg_servings", "fruit_servings", "status", "eaten_fraction",
    "logged_by", "reported_by", "confidence", "source", "notes",
    "created_at", "updated_at",
]

ENTRY_STATUSES = ("eaten", "packed", "partial", "returned")

# (nutrient name, entry/total field, kind, display unit)
NUTRIENT_TARGETS = [
    ("kcal", "kcal", "range", "kcal"),
    ("protein", "protein_g", "min", "g"),
    ("carbs", "carbs_g", "range", "g"),
    ("fat", "fat_g", "range", "g"),
    ("satfat", "satfat_g", "max", "g"),
    ("fibre", "fibre_g", "min", "g"),
    ("sugar", "sugar_g", "max", "g"),
    ("sodium", "sodium_mg", "max", "mg"),
    ("iron", "iron_mg", "min", "mg"),
    ("calcium", "calcium_mg", "min", "mg"),
    ("veg_servings", "veg_servings", "min", "srv"),
    ("fruit_servings", "fruit_servings", "min", "srv"),
    ("milk_ml", "milk_ml", "max", "ml"),
    ("water_ml", "water", "min", "ml"),
]

# Nutrients a child's day/summary/week may show (no kcal/carbs/fat/sugar/sodium).
CHILD_NUTRIENT_FIELDS = [
    "protein_g", "iron_mg", "calcium_mg", "fibre_g",
    "veg_servings", "fruit_servings", "milk_ml",
]
# Adult-only nutrient keys stripped from every child-facing JSON object.
CHILD_HIDDEN_KEYS = {
    "kcal", "carbs_g", "fat_g", "satfat_g", "sugar_g", "sodium_mg",
}
CHILD_TARGET_NAMES = {
    "protein", "iron", "calcium", "fibre",
    "veg_servings", "fruit_servings", "milk_ml",
}

# (key, value, kind, unit, note) seeded idempotently on init, per person.
_KCAL_NOTE = "maintenance ~2,600-2,800 at 80 kg active; mild deficit"
SEED_TARGETS = [
    ("kcal_lo", 2300, "range_lo", "kcal", _KCAL_NOTE),
    ("kcal_hi", 2600, "range_hi", "kcal", _KCAL_NOTE),
    ("protein", 140, "min", "g", None),
    ("carbs_lo", 250, "range_lo", "g", None),
    ("carbs_hi", 330, "range_hi", "g", None),
    ("fat_lo", 65, "range_lo", "g", None),
    ("fat_hi", 85, "range_hi", "g", None),
    ("satfat", 25, "max", "g", None),
    ("fibre", 32, "min", "g", None),
    ("sugar", 50, "max", "g", "added+total proxy"),
    ("sodium", 2300, "max", "mg", None),
    ("veg_servings", 5, "min", "srv", None),
    ("fruit_servings", 2, "min", "srv", None),
    # No water target (Sumeet 2026-10-12: "I obviously am not going to log each sip of water").
    # `water` still logs if he volunteers an amount; it is shown but never scored or nagged.
]

# Children: never a calorie target. Protein/iron/calcium per IOM DRI; veg/fruit
# in Canada's Food Guide style; fibre is the AI (with a realistic hand note).
SEED_TARGETS_TEGH = [  # 4-8 y
    ("protein", 19, "min", "g", "IOM DRI 4-8 y"),
    ("iron", 10, "min", "mg", "IOM DRI 4-8 y"),
    ("calcium", 1000, "min", "mg", "IOM DRI 4-8 y"),
    ("fibre", 25, "min", "g", "AI; realistic 15-20"),
    ("veg_servings", 5, "min", "srv", "Canada's Food Guide"),
    ("fruit_servings", 2, "min", "srv", "Canada's Food Guide"),
]
SEED_TARGETS_KIRAT = [  # 1-3 y
    ("protein", 13, "min", "g", "IOM DRI 1-3 y"),
    ("iron", 7, "min", "mg", "IOM DRI 1-3 y"),
    ("calcium", 700, "min", "mg", "IOM DRI 1-3 y"),
    ("fibre", 14, "min", "g", "AI; realistic 8-12"),
    ("veg_servings", 4, "min", "srv", "Canada's Food Guide"),
    ("fruit_servings", 2, "min", "srv", "Canada's Food Guide"),
    ("milk_ml", 500, "max", "ml",
     "toddler cow's milk > ~500 ml/day crowds out iron-rich foods"),
]
SEED_PERSON_TARGETS = {
    "sumeet": SEED_TARGETS,
    "tegh": SEED_TARGETS_TEGH,
    "kirat": SEED_TARGETS_KIRAT,
    # priyanka: none yet (she sets them later).
}

# (key, name, kind, birthday, sex, notes)
SEED_PEOPLE = [
    ("sumeet", "Sumeet", "adult", "1987-04-29", "M", None),
    ("priyanka", "Priyanka", "adult", "1986-03-11", "F", None),
    ("tegh", "Tegh", "child", "2022-04-12", "M", "JK student"),
    ("kirat", "Kirat", "child", "2025-02-15", "M",
     "daycare; congenital hypothyroidism, takes levothyroxine (Synthroid)"),
]

DISP_NAME = {
    "veg_servings": "veg", "fruit_servings": "fruit", "water_ml": "water",
    "iron_mg": "iron", "calcium_mg": "calcium", "milk_ml": "milk",
    "iron": "iron", "calcium": "calcium",
}

SIM_THRESHOLD = 0.6          # token-set similarity for dedup
DEDUP_WINDOW_S = 3 * 3600    # +/- 3h for dedup
EXIT_DUPLICATE = 3


class UserError(Exception):
    """A clean, user-facing error (printed to stderr, nonzero exit)."""


# --------------------------------------------------------------------------- #
# time + formatting helpers
# --------------------------------------------------------------------------- #
def now_dt():
    return datetime.now(TZ)


def now_iso():
    return now_dt().isoformat()


def parse_at(s):
    """Accept 'now', 'HH:MM' (today), 'YYYY-MM-DD HH:MM', or ISO8601."""
    if not s or s == "now":
        return now_dt()
    s = s.strip()
    # bare HH:MM -> today at that time, local
    if len(s) <= 5 and ":" in s:
        try:
            t = datetime.strptime(s, "%H:%M")
            n = now_dt()
            return n.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise UserError(f"could not parse --at value: {s!r} "
                    "(use 'now', 'HH:MM', 'YYYY-MM-DD HH:MM', or ISO8601)")


def resolve_day(spec):
    if not spec or spec == "today":
        return now_dt().date().isoformat()
    if spec == "yesterday":
        return (now_dt().date() - timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(spec, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise UserError(f"bad day: {spec!r} (use YYYY-MM-DD, today, or yesterday)")


def fmt_g(v):
    if v is None:
        return "-"
    if abs(v) < 10:
        return f"{v:.1f}"
    return str(round(v))


def fmt_val(v, unit):
    if v is None:
        return "-"
    if unit in ("kcal", "mg", "ml"):
        return str(round(v))
    return fmt_g(v)


def fmt_qty(v):
    if v is None:
        return "-"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:g}"


def fmt_total(totals, field, unit):
    """Format a total; if some entries lacked a value, show '>= X (n unknown)'."""
    v = totals.get(field)
    unknown = totals.get("_unknown", {}).get(field, 0)
    s = fmt_val(v, unit)
    if unknown:
        plural = "s" if unknown != 1 else ""
        return f">= {s} ({unknown} item{plural} unknown)"
    return s


# --------------------------------------------------------------------------- #
# DB
# --------------------------------------------------------------------------- #
def db_path():
    env = os.environ.get("NUTRITION_DB")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "data" / "nutrition.db"


def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_schema(conn)
    return conn


# v2 shapes. CREATE ... IF NOT EXISTS gives fresh DBs v2 directly; _migrate()
# brings an existing v1 DB up to these shapes.
_CREATE_V2 = """
CREATE TABLE IF NOT EXISTS people(
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('adult','child')),
  birthday TEXT,
  sex TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS foods(
  id INTEGER PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  aliases TEXT DEFAULT '',
  basis TEXT NOT NULL CHECK(basis IN ('100g','serving')),
  serving_g REAL,
  unit_name TEXT,
  density_g_ml REAL,
  kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL, satfat_g REAL,
  fibre_g REAL, sugar_g REAL, sodium_mg REAL, iron_mg REAL, calcium_mg REAL,
  veg_servings REAL DEFAULT 0, fruit_servings REAL DEFAULT 0,
  source TEXT, notes TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS entries(
  id INTEGER PRIMARY KEY,
  person TEXT NOT NULL DEFAULT 'sumeet' REFERENCES people(key),
  eaten_at TEXT NOT NULL,
  day TEXT NOT NULL,
  meal TEXT,
  food_id INTEGER REFERENCES foods(id),
  description TEXT NOT NULL,
  qty REAL NOT NULL,
  qty_unit TEXT NOT NULL,
  grams REAL,
  kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL, satfat_g REAL,
  fibre_g REAL, sugar_g REAL, sodium_mg REAL, iron_mg REAL, calcium_mg REAL,
  veg_servings REAL, fruit_servings REAL,
  status TEXT DEFAULT 'eaten' CHECK(status IN ('eaten','packed','partial','returned')),
  eaten_fraction REAL DEFAULT 1.0,
  logged_by TEXT, reported_by TEXT,
  confidence TEXT DEFAULT 'medium',
  source TEXT, notes TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_day ON entries(day);
CREATE TABLE IF NOT EXISTS water(
  id INTEGER PRIMARY KEY, person TEXT NOT NULL DEFAULT 'sumeet',
  day TEXT, ml REAL, at TEXT
);
CREATE TABLE IF NOT EXISTS targets(
  person TEXT NOT NULL DEFAULT 'sumeet',
  key TEXT NOT NULL,
  value REAL,
  kind TEXT CHECK(kind IN ('min','max','range_lo','range_hi')),
  unit TEXT, note TEXT,
  PRIMARY KEY(person, key)
);
CREATE TABLE IF NOT EXISTS body(
  id INTEGER PRIMARY KEY, person TEXT NOT NULL DEFAULT 'sumeet',
  day TEXT, metric TEXT, value REAL,
  source TEXT, at TEXT, UNIQUE(person,day,metric,source)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def _table_cols(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def get_meta(conn, key):
    r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def ensure_schema(conn):
    conn.executescript(_CREATE_V2)  # implicit commit
    try:
        conn.execute("BEGIN")
        _migrate(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate(conn):
    """Bring an existing v1 DB to v2: add columns, rebuild targets/body,
    seed people. Idempotent — safe to run on a fresh v2 DB or re-run."""
    # people always seeded (idempotent)
    for key, name, kind, bday, sex, notes in SEED_PEOPLE:
        conn.execute(
            "INSERT OR IGNORE INTO people(key,name,kind,birthday,sex,notes) "
            "VALUES (?,?,?,?,?,?)", (key, name, kind, bday, sex, notes))

    # entries: add v2 columns if missing (ALTER keeps existing rows intact)
    ecols = _table_cols(conn, "entries")
    entry_adds = [
        ("person", "TEXT NOT NULL DEFAULT 'sumeet'"),
        ("iron_mg", "REAL"),
        ("calcium_mg", "REAL"),
        ("status", "TEXT DEFAULT 'eaten' "
                   "CHECK(status IN ('eaten','packed','partial','returned'))"),
        ("eaten_fraction", "REAL DEFAULT 1.0"),
        ("logged_by", "TEXT"),
        ("reported_by", "TEXT"),
    ]
    for col, decl in entry_adds:
        if col not in ecols:
            conn.execute(f"ALTER TABLE entries ADD COLUMN {col} {decl}")

    # foods: add mineral + density columns if missing
    fcols = _table_cols(conn, "foods")
    for col in ("iron_mg", "calcium_mg", "density_g_ml"):
        if col not in fcols:
            conn.execute(f"ALTER TABLE foods ADD COLUMN {col} REAL")

    # water: add person if missing
    wcols = _table_cols(conn, "water")
    if "person" not in wcols:
        conn.execute("ALTER TABLE water ADD COLUMN person TEXT NOT NULL DEFAULT 'sumeet'")

    # targets: PK changed from (key) to (person,key) -> rebuild if old-shaped
    tcols = _table_cols(conn, "targets")
    if "person" not in tcols:
        conn.execute(
            "CREATE TABLE targets_v2("
            "person TEXT NOT NULL DEFAULT 'sumeet', key TEXT NOT NULL, value REAL,"
            "kind TEXT CHECK(kind IN ('min','max','range_lo','range_hi')),"
            "unit TEXT, note TEXT, PRIMARY KEY(person,key))")
        conn.execute(
            "INSERT INTO targets_v2(person,key,value,kind,unit,note) "
            "SELECT 'sumeet', key, value, kind, unit, note FROM targets")
        conn.execute("DROP TABLE targets")
        conn.execute("ALTER TABLE targets_v2 RENAME TO targets")

    # body: UNIQUE changed to (person,day,metric,source) -> rebuild if old-shaped
    bcols = _table_cols(conn, "body")
    if "person" not in bcols:
        conn.execute(
            "CREATE TABLE body_v2("
            "id INTEGER PRIMARY KEY, person TEXT NOT NULL DEFAULT 'sumeet',"
            "day TEXT, metric TEXT, value REAL, source TEXT, at TEXT,"
            "UNIQUE(person,day,metric,source))")
        conn.execute(
            "INSERT INTO body_v2(id,person,day,metric,value,source,at) "
            "SELECT id, 'sumeet', day, metric, value, source, at FROM body")
        conn.execute("DROP TABLE body")
        conn.execute("ALTER TABLE body_v2 RENAME TO body")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_person_day "
                 "ON entries(person, day)")
    # Seed per-person targets for anyone who has NONE yet (e.g. the kids after a v1->v2
    # migration). Never touches a person who already has targets, so edits made later stick.
    for person, rows in SEED_PERSON_TARGETS.items():
        if conn.execute("SELECT 1 FROM targets WHERE person=? LIMIT 1", (person,)).fetchone():
            continue
        for key, value, kind, unit, note in rows:
            conn.execute("INSERT OR IGNORE INTO targets(person,key,value,kind,unit,note) "
                         "VALUES (?,?,?,?,?,?)", (person, key, value, kind, unit, note))
    set_meta(conn, "schema_version", SCHEMA_VERSION)


# --------------------------------------------------------------------------- #
# people
# --------------------------------------------------------------------------- #
def get_person(conn, key):
    return conn.execute("SELECT * FROM people WHERE key=?",
                        (key.strip().lower(),)).fetchone()


def resolve_person(conn, args):
    """Resolve the active person from --person / NUTRITION_PERSON / 'sumeet'.
    Returns the people row; unknown person -> clear UserError."""
    p = getattr(args, "person", None) or os.environ.get("NUTRITION_PERSON") or "sumeet"
    row = get_person(conn, p)
    if row is None:
        known = [r["key"] for r in conn.execute(
            "SELECT key FROM people ORDER BY key").fetchall()]
        raise UserError(f"unknown person: {p!r} (known: {', '.join(known)})")
    return row


# --------------------------------------------------------------------------- #
# foods
# --------------------------------------------------------------------------- #
def upsert_food(conn, data):
    data = dict(data)
    data.setdefault("aliases", "")
    data["aliases"] = (data.get("aliases") or "").lower()
    data.setdefault("veg_servings", 0)
    data.setdefault("fruit_servings", 0)
    data["updated_at"] = now_iso()
    cols = [c for c in FOOD_COLS if c in data]
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "key")
    sql = (f"INSERT INTO foods ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT(key) DO UPDATE SET {updates}")
    conn.execute(sql, [data[c] for c in cols])
    conn.commit()


def get_food(conn, key):
    return conn.execute("SELECT * FROM foods WHERE key=?", (key.strip().lower(),)).fetchone()


def find_matches(conn, query, limit=10):
    q = query.strip().lower()
    out = []
    for r in conn.execute("SELECT * FROM foods").fetchall():
        key, name = r["key"].lower(), r["name"].lower()
        aliases = [a.strip() for a in (r["aliases"] or "").split(",") if a.strip()]
        if q == key or q in aliases:
            rank = 0
        elif key.startswith(q) or name.startswith(q) or any(a.startswith(q) for a in aliases):
            rank = 1
        elif q in key or q in name or any(q in a for a in aliases):
            rank = 2
        else:
            continue
        out.append((rank, r["key"], r))
    out.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in out][:limit]


def suggest_keys(conn, key, limit=3):
    sugg = [s["key"] for s in find_matches(conn, key, limit=limit)]
    if sugg:
        return sugg
    # fuzzy fallback for typos (e.g. 'chikken' -> 'chicken_*')
    import difflib
    pool = []
    for r in conn.execute("SELECT key, aliases FROM foods").fetchall():
        pool.append(r["key"])
        pool.extend(a.strip() for a in (r["aliases"] or "").split(",") if a.strip())
    close = difflib.get_close_matches(key.lower(), pool, n=limit, cutoff=0.6)
    # map any matched alias back to its key
    out = []
    for m in close:
        r = conn.execute(
            "SELECT key FROM foods WHERE key=? OR instr(','||aliases||',', ?)>0",
            (m, "," + m + ",")).fetchone()
        if r and r["key"] not in out:
            out.append(r["key"])
    return out[:limit]


def require_food(conn, key):
    f = get_food(conn, key)
    if f is None:
        sugg = suggest_keys(conn, key, limit=3)
        msg = f"unknown food key: {key!r}"
        if sugg:
            msg += "\n  did you mean: " + ", ".join(sugg)
        raise UserError(msg)
    return f


# --------------------------------------------------------------------------- #
# unit resolution + nutrient computation
# --------------------------------------------------------------------------- #
# Per-food extra unit words that map to the food's own unit_name. Rice is
# scooped by the katori at home, same portion as its CNF 'cup' (160 g).
ALIAS_UNITS = {
    "rice_white": {"katori", "katoris"},
}

# Volume words -> canonical volume token (for drinks only).
VOLUME_UNITS = {
    "ml": "ml", "millilitre": "ml", "millilitres": "ml",
    "milliliter": "ml", "milliliters": "ml",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "glass": "glass", "glasses": "glass",
    "cup": "cup", "cups": "cup",
}
# ml per one canonical volume token.
VOLUME_ML = {"ml": 1.0, "l": 1000.0, "glass": 250.0, "cup": 250.0}

# Fallback liquid detection when density_g_ml isn't set on the food.
LIQUID_KEY_PREFIXES = ("milk", "chai", "juice", "lassi", "buttermilk",
                       "coffee", "tea", "water")
_DENSE_LIQUID_PREFIXES = ("milk", "lassi", "buttermilk", "chai")


def _food_get(food, col):
    """Column accessor tolerant of sqlite3.Row (no .get) and plain dicts."""
    try:
        keys = food.keys()
    except AttributeError:
        keys = ()
    return food[col] if col in keys else None


def food_density(food):
    """Return (is_liquid, density_g_ml) for a food.

    A food is liquid when density_g_ml is set, OR (fallback) its key matches a
    known drink prefix / is canada_dry_zero. Fallback density is 1.03 for
    milk/lassi/buttermilk/chai, else 1.0."""
    d = _food_get(food, "density_g_ml")
    if d is not None:
        return True, d
    key = (food["key"] or "").lower()
    is_liquid = key == "canada_dry_zero" or any(
        key.startswith(p) for p in LIQUID_KEY_PREFIXES)
    if not is_liquid:
        return False, None
    if any(key.startswith(p) for p in _DENSE_LIQUID_PREFIXES):
        return True, 1.03
    return True, 1.0


def norm_unit(food, raw):
    """Return canonical token: 'g', 'serving', the food's unit_name, or — for
    drinks — a volume token ('ml'/'l'/'glass'/'cup')."""
    if raw is None:
        if food["basis"] == "serving":
            return food["unit_name"] or "serving"
        if food["basis"] == "100g" and food["unit_name"]:
            return food["unit_name"]
        return "g"
    u = raw.strip().lower()
    if u in ("g", "gram", "grams", "gm", "gms"):
        return "g"
    if u in ("serving", "servings", "x"):
        return "serving"
    un = (food["unit_name"] or "").lower()
    if un and u in (un, un + "s"):
        return food["unit_name"]
    if u in ALIAS_UNITS.get((food["key"] or "").lower(), ()):
        return food["unit_name"]
    if u in ("unit", "units"):
        return food["unit_name"] or "serving"
    if u in VOLUME_UNITS:
        # 'cup'/'cups' matching the food's own unit_name was handled above.
        if food_density(food)[0]:
            return VOLUME_UNITS[u]
        raise UserError(
            f"bad unit {raw!r} for {food['key']}: it isn't a drink; "
            f"use 'g', 'serving'/'x'"
            + (f", or '{food['unit_name']}'" if food["unit_name"] else "")
            + " (ml/glass/cup work for drinks like milk/chai/juice)")
    raise UserError(
        f"bad unit {raw!r} for {food['key']}: "
        f"use 'g', 'serving'/'x'"
        + (f", or '{food['unit_name']}'" if food["unit_name"] else ""))


def compute_snapshot(food, qty, token):
    """Return (snapshot dict with FOOD_NUTRIENTS + grams, grams, servings)."""
    serving_g = food["serving_g"]
    basis = food["basis"]
    if token == "g":
        grams = qty
        servings = (grams / serving_g) if serving_g else None
    elif token in VOLUME_ML and token != (food["unit_name"] or "").lower():
        # drink logged by a volume unit -> grams via density. 'cup' matching the
        # food's own unit_name (e.g. chai, rice) is a serving count, not volume.
        _, density = food_density(food)
        if density is None:
            raise UserError(
                f"cannot convert {token} for {food['key']}: no density set")
        grams = qty * VOLUME_ML[token] * density
        servings = (grams / serving_g) if serving_g else None
    else:  # count of servings / units
        servings = qty
        grams = (qty * serving_g) if serving_g else None

    if basis == "100g":
        if grams is None:
            raise UserError(
                f"cannot compute {food['key']}: give grams, or set serving_g "
                f"to log by {token}")
        factor = grams / 100.0
    else:  # serving basis
        if servings is None:
            raise UserError(
                f"cannot compute {food['key']}: needs serving_g to convert "
                f"grams into servings")
        factor = servings

    snap = {}
    for f in FOOD_NUTRIENTS:
        v = food[f]
        snap[f] = (v * factor) if v is not None else None
    snap["grams"] = grams
    return snap, grams, servings


# --------------------------------------------------------------------------- #
# entries
# --------------------------------------------------------------------------- #
def insert_entry(conn, row):
    cols = [c for c in ENTRY_COLS if c in row]
    placeholders = ",".join("?" * len(cols))
    cur = conn.execute(
        f"INSERT INTO entries ({','.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols])
    conn.commit()
    return cur.lastrowid


def get_entry(conn, eid):
    r = conn.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
    if r is None:
        raise UserError(f"no entry with id {eid}")
    return r


def _given_person(args):
    """The person the caller explicitly asked for via --person or
    NUTRITION_PERSON, or None if neither was set (the implicit 'sumeet' default
    is NOT treated as 'given')."""
    p = getattr(args, "person", None) or os.environ.get("NUTRITION_PERSON")
    return p.strip().lower() if p else None


def require_entry_person_match(conn, args, entry):
    """For id-pinned commands (eaten/rm/edit): the entry itself pins the person.
    If the caller passed a --person that names someone else, refuse — don't
    silently touch another person's entry. A valid --person is checked for
    existence so a typo still errors."""
    given = _given_person(args)
    if given is None:
        return
    if get_person(conn, given) is None:
        resolve_person(conn, args)  # raises the standard unknown-person error
    if given != entry["person"]:
        raise UserError(
            f"entry #{entry['id']} belongs to {entry['person']}, not {given!r} "
            f"(the entry id already pins the person; drop --person or fix it)")


def entry_to_dict(r):
    return {k: r[k] for k in r.keys()}


def _frac(r):
    f = r["eaten_fraction"]
    return 1.0 if f is None else f


def is_milk_food(key):
    return bool(key) and key.lower().startswith("milk")


def day_totals(conn, day, person="sumeet"):
    """Totals for one person-day. Counts nutrient * eaten_fraction. NULL nutrient
    values are *not* summed as 0; their count is tracked in totals['_unknown']."""
    totals = {f: 0.0 for f in FOOD_NUTRIENTS}
    unknown = {f: 0 for f in FOOD_NUTRIENTS}
    milk_ml = 0.0
    rows = conn.execute(
        "SELECT e.*, f.key AS food_key, f.density_g_ml AS food_density FROM entries e "
        "LEFT JOIN foods f ON e.food_id=f.id WHERE e.day=? AND e.person=?",
        (day, person)).fetchall()
    for r in rows:
        frac = _frac(r)
        for f in FOOD_NUTRIENTS:
            v = r[f]
            if v is None:
                unknown[f] += 1
            else:
                totals[f] += v * frac
        if is_milk_food(r["food_key"]) and r["grams"] is not None:
            # grams -> ml via density when known (milk density ~1.03 > 1).
            dens = r["food_density"]
            ml = (r["grams"] / dens) if dens else r["grams"]
            milk_ml += ml * frac
    totals["milk_ml"] = milk_ml
    water = conn.execute(
        "SELECT COALESCE(SUM(ml),0) FROM water WHERE day=? AND person=?",
        (day, person)).fetchone()[0]
    totals["water"] = water or 0.0
    totals["_unknown"] = unknown
    return totals


# --------------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------------- #
def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def desc_similarity(a, b):
    """Token-set (Jaccard) similarity of two descriptions, 0..1."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def find_duplicates(conn, person, day, food_id, desc, dt):
    """Existing entries for same person+day that look like this one:
    (same food_id OR description similarity >= 0.6) AND |time diff| <= 3h."""
    matches = []
    rows = conn.execute(
        "SELECT * FROM entries WHERE person=? AND day=? ORDER BY eaten_at, id",
        (person, day)).fetchall()
    for r in rows:
        try:
            rt = datetime.fromisoformat(r["eaten_at"])
        except (ValueError, TypeError):
            continue
        try:
            diff = abs((dt - rt).total_seconds())
        except TypeError:
            continue
        if diff > DEDUP_WINDOW_S:
            continue
        same_food = food_id is not None and r["food_id"] == food_id
        if same_food or desc_similarity(desc, r["description"]) >= SIM_THRESHOLD:
            matches.append(r)
    return matches


def _match_summary(r):
    return {
        "id": r["id"],
        "eaten_at": r["eaten_at"],
        "time": (r["eaten_at"][11:16] if r["eaten_at"] else "--:--"),
        "description": r["description"],
        "qty": r["qty"],
        "qty_unit": r["qty_unit"],
        "logged_by": r["logged_by"],
        "reported_by": r["reported_by"],
    }


def _emit_duplicate(args, matches):
    mlist = [_match_summary(r) for r in matches]
    if getattr(args, "json", False):
        print(json.dumps({"duplicate": True, "matches": mlist}, default=str))
    else:
        lines = ["POSSIBLE DUPLICATE — nothing was written (use --force to log anyway).",
                 f"  {len(matches)} existing entr"
                 f"{'y' if len(matches) == 1 else 'ies'} within 3h:"]
        for m in mlist:
            lines.append(
                f"    #{m['id']} {m['time']} {m['description']} "
                f"[{fmt_qty(m['qty'])} {m['qty_unit']}] "
                f"logged_by={m['logged_by'] or '-'} "
                f"reported_by={m['reported_by'] or '-'}")
        print("\n".join(lines))


# --------------------------------------------------------------------------- #
# targets
# --------------------------------------------------------------------------- #
def get_targets(conn, person="sumeet"):
    return {r["key"]: r for r in conn.execute(
        "SELECT * FROM targets WHERE person=?", (person,)).fetchall()}


def eval_target(nut_def, total, targets):
    """Return a status dict for one nutrient, or None if no target set."""
    name, field, kind, unit = nut_def
    res = {"nutrient": name, "field": field, "kind": kind, "unit": unit,
           "total": total, "shortfall_pct": 0.0}
    if kind == "range":
        lo_r, hi_r = targets.get(name + "_lo"), targets.get(name + "_hi")
        if not lo_r or not hi_r:
            return None
        lo, hi = lo_r["value"], hi_r["value"]
        res["lo"], res["hi"] = lo, hi
        if total < lo:
            res["state"] = "below"
            res["status"] = f"↓ below, need {fmt_val(lo - total, unit)}{unit}"
            res["shortfall_pct"] = (lo - total) / lo if lo else 0.0
        elif total <= hi:
            res["state"] = "in"
            res["status"] = "in range"
        else:
            res["state"] = "above"
            res["status"] = f"⚠️ above by {fmt_val(total - hi, unit)}{unit}"
    else:
        row = targets.get(name)
        if not row:
            return None
        tgt = row["value"]
        res["target"] = tgt
        if kind == "min":
            if total >= tgt:
                res["state"] = "ok"
                res["status"] = "✅"
            else:
                res["state"] = "under"
                res["status"] = f"↓ need {fmt_val(tgt - total, unit)}{unit}"
                res["shortfall_pct"] = (tgt - total) / tgt if tgt else 0.0
        else:  # max
            if total > tgt:
                res["state"] = "over"
                res["status"] = f"⚠️ over by {fmt_val(total - tgt, unit)}{unit}"
            else:
                res["state"] = "ok"
                res["status"] = f"ok ({fmt_val(tgt - total, unit)}{unit} left)"
    return res


def target_statuses(conn, totals, person="sumeet"):
    targets = get_targets(conn, person)
    out = []
    for nd in NUTRIENT_TARGETS:
        st = eval_target(nd, totals[nd[1]], targets)
        if st:
            out.append(st)
    return out


def best_levers(statuses, n=2):
    short = [s for s in statuses if s["shortfall_pct"] > 0]
    short.sort(key=lambda s: s["shortfall_pct"], reverse=True)
    return [DISP_NAME.get(s["nutrient"], s["nutrient"]) for s in short[:n]]


MISS_STATES = {"under", "below", "over", "above"}


# --------------------------------------------------------------------------- #
# output helper
# --------------------------------------------------------------------------- #
def strip_child_keys(obj):
    """Recursively drop adult-only nutrient keys (kcal/carbs/fat/satfat/sugar/
    sodium) from a child-facing object, in place-ish. Values stay in the DB;
    this only shapes JSON output. _unknown sub-maps are pruned too."""
    if isinstance(obj, dict):
        return {k: strip_child_keys(v) for k, v in obj.items()
                if k not in CHILD_HIDDEN_KEYS}
    if isinstance(obj, list):
        return [strip_child_keys(v) for v in obj]
    return obj


def emit(args, human, obj, child=False):
    if getattr(args, "json", False):
        if child:
            obj = strip_child_keys(obj)
        print(json.dumps(obj, default=str))
    else:
        print(human)


# --------------------------------------------------------------------------- #
# command handlers
# --------------------------------------------------------------------------- #
def cmd_init(conn, args):
    for person, rows in SEED_PERSON_TARGETS.items():
        for key, value, kind, unit, note in rows:
            conn.execute(
                "INSERT OR IGNORE INTO targets(person,key,value,kind,unit,note) "
                "VALUES (?,?,?,?,?,?)", (person, key, value, kind, unit, note))
    set_meta(conn, "schema_version", SCHEMA_VERSION)
    seed_path = Path(__file__).resolve().parent / "seed_foods.json"
    loaded = 0
    if seed_path.exists():
        foods = json.loads(seed_path.read_text())
        for food in foods:
            data = {k: food.get(k) for k in FOOD_COLS if k in food}
            upsert_food(conn, data)
            loaded += 1
    conn.commit()
    nfoods = conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
    ntargets = conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
    npeople = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    emit(args, f"initialized db at {db_path()} — {nfoods} foods, "
               f"{npeople} people, {ntargets} target rows (loaded {loaded} seed foods)",
         {"db": str(db_path()), "foods": nfoods, "people": npeople,
          "targets": ntargets, "seed_loaded": loaded})


# ----- person ----- #
def cmd_person(conn, args):
    sub = args.person_cmd
    if sub == "list":
        rows = conn.execute("SELECT * FROM people ORDER BY kind, key").fetchall()
        lines = [f"{r['key']:<10} {r['kind']:<6} {r['name']:<10} "
                 f"{r['birthday'] or '-':<12} {r['sex'] or '-':<2} "
                 f"{r['notes'] or ''}" for r in rows]
        emit(args, "\n".join(lines) if lines else "(no people)",
             {"people": [entry_to_dict(r) for r in rows]})
    elif sub == "add":
        key = args.key.strip().lower()
        if get_person(conn, key):
            raise UserError(f"person {key!r} already exists (use person edit)")
        conn.execute(
            "INSERT INTO people(key,name,kind,birthday,sex,notes) VALUES (?,?,?,?,?,?)",
            (key, args.name, args.kind, args.birthday, args.sex, args.notes))
        conn.commit()
        emit(args, f"added person {key} ({args.kind})",
             entry_to_dict(get_person(conn, key)))
    elif sub == "edit":
        row = get_person(conn, args.key)
        if row is None:
            raise UserError(f"unknown person: {args.key!r}")
        fields = {}
        for a in ("name", "kind", "birthday", "sex", "notes"):
            v = getattr(args, a, None)
            if v is not None:
                fields[a] = v
        if not fields:
            raise UserError("person edit: nothing to change")
        conn.execute(
            f"UPDATE people SET {','.join(k + '=?' for k in fields)} WHERE key=?",
            list(fields.values()) + [row["key"]])
        conn.commit()
        emit(args, f"updated person {row['key']}", entry_to_dict(get_person(conn, row["key"])))


def _food_data_from_args(args):
    data = {}
    mapping = {
        "name": "name", "basis": "basis", "serving_g": "serving_g",
        "unit": "unit_name", "kcal": "kcal", "protein": "protein_g",
        "carbs": "carbs_g", "fat": "fat_g", "satfat": "satfat_g",
        "fibre": "fibre_g", "sugar": "sugar_g", "sodium": "sodium_mg",
        "iron": "iron_mg", "calcium": "calcium_mg",
        "veg": "veg_servings", "fruit": "fruit_servings", "aliases": "aliases",
        "source": "source", "notes": "notes",
    }
    for a, col in mapping.items():
        v = getattr(args, a, None)
        if v is not None:
            data[col] = v
    return data


def cmd_food(conn, args):
    sub = args.food_cmd
    if sub == "add":
        data = _food_data_from_args(args)
        data["key"] = args.key.strip().lower()
        data["name"] = args.name
        data["basis"] = args.basis
        upsert_food(conn, data)
        f = get_food(conn, data["key"])
        emit(args, f"saved food {f['key']} ({f['name']})", entry_to_dict(f))
    elif sub == "find":
        matches = find_matches(conn, args.query)
        rows = []
        for m in matches:
            unit = m["unit_name"] or (f"{fmt_qty(m['serving_g'])}g" if m["serving_g"] else "-")
            rows.append({"key": m["key"], "name": m["name"], "basis": m["basis"],
                         "unit": unit, "serving_g": m["serving_g"],
                         "protein_g": m["protein_g"], "kcal": m["kcal"],
                         "iron_mg": m["iron_mg"], "calcium_mg": m["calcium_mg"]})
        lines = [f"{r['key']:<16} {r['name']:<34} {r['basis']:<7} "
                 f"{str(r['unit']):<10} P{fmt_g(r['protein_g'])} {fmt_val(r['kcal'],'kcal')}kcal"
                 for r in rows]
        emit(args, "\n".join(lines) if lines else "(no matches)",
             {"query": args.query, "matches": rows})
    elif sub == "show":
        f = require_food(conn, args.key)
        emit(args, "\n".join(f"{k}: {f[k]}" for k in f.keys()), entry_to_dict(f))
    elif sub == "edit":
        f = require_food(conn, args.key)
        data = _food_data_from_args(args)
        if not data:
            raise UserError("food edit: nothing to change")
        data["key"] = f["key"]
        data["name"] = data.get("name", f["name"])
        data["basis"] = data.get("basis", f["basis"])
        upsert_food(conn, data)
        f = get_food(conn, f["key"])
        emit(args, f"updated food {f['key']}", entry_to_dict(f))
    elif sub == "rm":
        f = require_food(conn, args.key)
        n = conn.execute("SELECT COUNT(*) FROM entries WHERE food_id=?",
                         (f["id"],)).fetchone()[0]
        if n > 0 and not args.force:
            raise UserError(
                f"{f['key']} is referenced by {n} entries; use --force to delete anyway")
        conn.execute("DELETE FROM foods WHERE id=?", (f["id"],))
        conn.commit()
        emit(args, f"deleted food {f['key']} ({n} entries kept with snapshots)",
             {"deleted": f["key"], "entries_referencing": n})


def _logged_by(args):
    return getattr(args, "logged_by", None) or os.environ.get("NUTRITION_AGENT") or "hermes"


def find_meal_conflict(conn, person, day, meal, dt, exclude_ids):
    """A packed/eaten entry for the same person+day+meal within 3h that isn't
    one of the dedup matches (exclude_ids). Returns the earliest such row or
    None — used to warn 'is this the same lunchbox?' on a child's --packed."""
    if not meal:
        return None
    rows = conn.execute(
        "SELECT * FROM entries WHERE person=? AND day=? AND meal=? "
        "AND status IN ('packed','eaten') ORDER BY eaten_at, id",
        (person, day, meal)).fetchall()
    for r in rows:
        if r["id"] in exclude_ids:
            continue
        try:
            rt = datetime.fromisoformat(r["eaten_at"])
            diff = abs((dt - rt).total_seconds())
        except (ValueError, TypeError):
            continue
        if diff <= DEDUP_WINDOW_S:
            return r
    return None


def _meal_conflict_note(person, meal, r):
    t = r["eaten_at"][11:16] if r["eaten_at"] else "--:--"
    return (f"NOTE: {person} already has {meal} items packed at {t} "
            f"(#{r['id']} {r['description']}). Is this the same lunchbox?")


def cmd_log(conn, args):
    person = resolve_person(conn, args)
    food = require_food(conn, args.food)
    token = norm_unit(food, args.unit)
    snap, grams, servings = compute_snapshot(food, args.qty, token)
    dt = parse_at(args.at)
    desc = args.desc or food["name"]
    day = dt.date().isoformat()

    matches = find_duplicates(conn, person["key"], day, food["id"], desc, dt)
    notes = args.notes
    if matches:
        if not args.force:
            _emit_duplicate(args, matches)
            return EXIT_DUPLICATE
        notes = ((notes + "; ") if notes else "") + "confirmed not a duplicate"

    status = "packed" if getattr(args, "packed", False) else "eaten"
    # Warn (don't block) if a child's packed meal looks like a second lunchbox.
    conflict = None
    if status == "packed" and person["kind"] == "child":
        conflict = find_meal_conflict(
            conn, person["key"], day, args.meal, dt, {m["id"] for m in matches})
    row = {
        "person": person["key"], "eaten_at": dt.isoformat(), "day": day,
        "meal": args.meal, "food_id": food["id"], "description": desc,
        "qty": args.qty, "qty_unit": token, "grams": grams,
        "status": status, "eaten_fraction": 1.0,
        "logged_by": _logged_by(args), "reported_by": args.reported_by,
        "confidence": args.confidence, "source": args.source,
        "notes": notes, "created_at": now_iso(), "updated_at": now_iso(),
    }
    row.update(snap)
    eid = insert_entry(conn, row)
    note = _meal_conflict_note(person["key"], args.meal, conflict) if conflict else None
    _emit_logged(args, get_entry(conn, eid), conn, person, note=note)


def cmd_log_custom(conn, args):
    person = resolve_person(conn, args)
    dt = parse_at(args.at)
    day = dt.date().isoformat()

    matches = find_duplicates(conn, person["key"], day, None, args.desc, dt)
    notes = args.notes
    if matches:
        if not args.force:
            _emit_duplicate(args, matches)
            return EXIT_DUPLICATE
        notes = ((notes + "; ") if notes else "") + "confirmed not a duplicate"

    status = "packed" if getattr(args, "packed", False) else "eaten"
    row = {
        "person": person["key"], "eaten_at": dt.isoformat(), "day": day,
        "meal": args.meal, "food_id": None, "description": args.desc,
        "qty": 1, "qty_unit": "serving", "grams": None,
        "status": status, "eaten_fraction": 1.0,
        "logged_by": _logged_by(args), "reported_by": args.reported_by,
        "confidence": args.confidence, "source": args.source,
        "notes": notes, "created_at": now_iso(), "updated_at": now_iso(),
    }
    for f in FOOD_NUTRIENTS:
        row[f] = None
    mapping = {"kcal": "kcal", "protein": "protein_g", "carbs": "carbs_g",
               "fat": "fat_g", "satfat": "satfat_g", "fibre": "fibre_g",
               "sugar": "sugar_g", "sodium": "sodium_mg", "iron": "iron_mg",
               "calcium": "calcium_mg", "veg": "veg_servings", "fruit": "fruit_servings"}
    for a, col in mapping.items():
        v = getattr(args, a, None)
        if v is not None:
            row[col] = v
    eid = insert_entry(conn, row)
    _emit_logged(args, get_entry(conn, eid), conn, person)


def _emit_logged(args, r, conn, person, note=None):
    totals = day_totals(conn, r["day"], person["key"])
    tag = f" [{r['status']}]" if r["status"] != "eaten" else ""
    if person["kind"] == "child":
        human = (f"logged #{r['id']} ({person['key']}) {r['description']} "
                 f"{fmt_qty(r['qty'])} {r['qty_unit']}{tag} → "
                 f"P {fmt_g(r['protein_g'])}g, iron {fmt_val(r['iron_mg'], 'mg')}mg"
                 f"  [day: P {fmt_g(totals['protein_g'])}g]")
    else:
        human = (f"logged #{r['id']} ({person['key']}) {r['description']} "
                 f"{fmt_qty(r['qty'])} {r['qty_unit']}{tag} → "
                 f"P {fmt_g(r['protein_g'])}g, {fmt_val(r['kcal'], 'kcal')} kcal"
                 f"  [day: P {fmt_g(totals['protein_g'])}g / "
                 f"{fmt_val(totals['kcal'], 'kcal')} kcal]")
    if note:
        human += "\n" + note
    obj = entry_to_dict(r)
    if note:
        obj["note"] = note
    emit(args, human, obj, child=(person["kind"] == "child"))


def cmd_edit(conn, args):
    r = get_entry(conn, args.id)
    require_entry_person_match(conn, args, r)
    row = entry_to_dict(r)
    changed_qty = False
    if args.qty is not None:
        row["qty"] = args.qty
        changed_qty = True
    if args.unit is not None:
        row["qty_unit"] = args.unit
        changed_qty = True
    if args.meal is not None:
        row["meal"] = args.meal
    if args.desc is not None:
        row["description"] = args.desc
    if args.notes is not None:
        row["notes"] = args.notes
    if args.confidence is not None:
        row["confidence"] = args.confidence
    if getattr(args, "reported_by", None) is not None:
        row["reported_by"] = args.reported_by
    if getattr(args, "logged_by", None) is not None:
        row["logged_by"] = args.logged_by
    if args.at is not None:
        dt = parse_at(args.at)
        row["eaten_at"] = dt.isoformat()
        row["day"] = dt.date().isoformat()

    if changed_qty and row["food_id"] is not None:
        food = conn.execute("SELECT * FROM foods WHERE id=?",
                            (row["food_id"],)).fetchone()
        if food is None:
            raise UserError("cannot recompute: food row was deleted")
        token = norm_unit(food, row["qty_unit"])
        snap, grams, _ = compute_snapshot(food, row["qty"], token)
        row["qty_unit"] = token
        row["grams"] = grams
        row.update(snap)
    elif changed_qty and row["food_id"] is None:
        raise UserError("cannot recompute a custom entry from qty; "
                        "edit nutrients via rm + log-custom")

    row["updated_at"] = now_iso()
    sets = [c for c in ENTRY_COLS if c in row]
    conn.execute(f"UPDATE entries SET {','.join(c + '=?' for c in sets)} WHERE id=?",
                 [row[c] for c in sets] + [args.id])
    conn.commit()
    r = get_entry(conn, args.id)
    emit(args, f"updated entry #{args.id} → P {fmt_g(r['protein_g'])}g, "
               f"{fmt_val(r['kcal'], 'kcal')} kcal", entry_to_dict(r))


def cmd_eaten(conn, args):
    r = get_entry(conn, args.id)
    require_entry_person_match(conn, args, r)
    if args.none:
        frac = 0.0
    elif args.all:
        frac = 1.0
    elif args.fraction is not None:
        frac = args.fraction
    else:
        raise UserError("eaten: give --fraction F, --all, or --none")
    if frac < 0 or frac > 1:
        raise UserError("eaten: fraction must be between 0 and 1")
    if abs(frac - 1.0) < 1e-9:
        status = "eaten"
    elif frac == 0.0:
        status = "returned"
    else:
        status = "partial"
    notes = r["notes"]
    if args.note:
        notes = ((notes + "; ") if notes else "") + args.note
    conn.execute(
        "UPDATE entries SET eaten_fraction=?, status=?, notes=?, updated_at=? WHERE id=?",
        (frac, status, notes, now_iso(), args.id))
    conn.commit()
    r = get_entry(conn, args.id)
    emit(args, f"entry #{args.id} → {status} (eaten_fraction={fmt_qty(frac)})",
         entry_to_dict(r))


def cmd_rm(conn, args):
    removed = []
    for eid in args.ids:
        r = get_entry(conn, eid)  # raises if missing
        require_entry_person_match(conn, args, r)
        conn.execute("DELETE FROM entries WHERE id=?", (eid,))
        removed.append(eid)
    conn.commit()
    emit(args, f"deleted {len(removed)} entr{'y' if len(removed) == 1 else 'ies'}: "
               + ", ".join(f"#{e}" for e in removed),
         {"deleted": removed})


def _entry_line(e, kind):
    t = e["eaten_at"][11:16] if e["eaten_at"] else "--:--"
    tag = f" [{e['status']}]" if e["status"] and e["status"] != "eaten" else ""
    if kind == "child":
        nut = (f"P{fmt_g(e['protein_g'])} Fe{fmt_val(e['iron_mg'], 'mg')} "
               f"Ca{fmt_val(e['calcium_mg'], 'mg')} Fib{fmt_g(e['fibre_g'])}")
    else:
        nut = (f"P{fmt_g(e['protein_g'])} {fmt_val(e['kcal'], 'kcal')}kcal "
               f"Fib{fmt_g(e['fibre_g'])}")
    return (f"  #{e['id']} {t} {e['meal'] or '-':<9} {e['description']} "
            f"[{fmt_qty(e['qty'])} {e['qty_unit']}]{tag} {nut}")


def _child_totals_line(totals):
    return (f"Totals: P {fmt_g(totals['protein_g'])}g, "
            f"iron {fmt_total(totals, 'iron_mg', 'mg')}mg, "
            f"calcium {fmt_total(totals, 'calcium_mg', 'mg')}mg, "
            f"fibre {fmt_g(totals['fibre_g'])}g, "
            f"veg {fmt_g(totals['veg_servings'])}, fruit {fmt_g(totals['fruit_servings'])}, "
            f"milk {fmt_val(totals['milk_ml'], 'ml')}ml")


def _adult_totals_line(totals):
    return (f"Totals: {fmt_val(totals['kcal'], 'kcal')} kcal, "
            f"P {fmt_g(totals['protein_g'])}g, C {fmt_g(totals['carbs_g'])}g, "
            f"Fat {fmt_g(totals['fat_g'])}g, Sat {fmt_g(totals['satfat_g'])}g, "
            f"Fib {fmt_g(totals['fibre_g'])}g, Sug {fmt_g(totals['sugar_g'])}g, "
            f"Na {fmt_val(totals['sodium_mg'], 'mg')}mg, "
            f"veg {fmt_g(totals['veg_servings'])}, fruit {fmt_g(totals['fruit_servings'])}, "
            f"water {fmt_val(totals['water'], 'ml')}ml")


def cmd_day(conn, args):
    person = resolve_person(conn, args)
    pkey, kind = person["key"], person["kind"]
    day = resolve_day(args.day)
    entries = conn.execute(
        "SELECT * FROM entries WHERE day=? AND person=? ORDER BY eaten_at, id",
        (day, pkey)).fetchall()
    totals = day_totals(conn, day, pkey)
    statuses = target_statuses(conn, totals, pkey)
    if kind == "child":
        statuses = [s for s in statuses if s["nutrient"] in CHILD_TARGET_NAMES]
    levers = best_levers(statuses)

    elist = [entry_to_dict(e) for e in entries]
    lines = [f"Day {day} — {pkey} ({kind})"]
    for e in entries:
        lines.append(_entry_line(e, kind))
    if not entries:
        lines.append("  (no entries)")
    lines.append(_child_totals_line(totals) if kind == "child"
                 else _adult_totals_line(totals))
    lines.append("Targets:")
    for s in statuses:
        lines.append(f"  {s['nutrient']}: {fmt_val(s['total'], s['unit'])}{s['unit']} "
                     f"{s['status']}")
    if not statuses:
        lines.append("  (no targets set)")
    if levers:
        lines.append("Next best levers: " + ", ".join(levers))
    emit(args, "\n".join(lines),
         {"person": pkey, "kind": kind, "day": day, "entries": elist,
          "totals": totals, "targets": statuses, "levers": levers},
         child=(kind == "child"))


def cmd_summary(conn, args):
    person = resolve_person(conn, args)
    pkey, kind = person["key"], person["kind"]
    day = resolve_day(args.day)
    totals = day_totals(conn, day, pkey)
    statuses = {s["nutrient"]: s for s in target_statuses(conn, totals, pkey)}

    def line(nut):
        s = statuses.get(nut)
        if not s:
            return None
        return f"{nut} {fmt_val(s['total'], s['unit'])}{s['unit']} {s['status']}"

    if kind == "child":
        child_statuses = {k: v for k, v in statuses.items()
                          if k in CHILD_TARGET_NAMES}
        levers = best_levers(list(child_statuses.values()))
        lines = [
            f"{day} {pkey}  "
            f"P{fmt_g(totals['protein_g'])} "
            f"Fe{fmt_total(totals, 'iron_mg', 'mg')} "
            f"Ca{fmt_total(totals, 'calcium_mg', 'mg')}",
            f"fibre {fmt_g(totals['fibre_g'])}g | veg {fmt_g(totals['veg_servings'])} | "
            f"fruit {fmt_g(totals['fruit_servings'])}"
            + (f" | milk {fmt_val(totals['milk_ml'], 'ml')}ml" if totals['milk_ml'] else ""),
        ]
        vs = [line(n) for n in ("protein", "iron", "calcium", "fibre")]
        vs = [x for x in vs if x]
        if vs:
            lines.append("vs targets: " + "; ".join(vs))
        if levers:
            lines.append("levers: " + ", ".join(levers))
        emit(args, "\n".join(lines),
             {"person": pkey, "kind": kind, "day": day, "totals": totals,
              "targets": list(child_statuses.values()), "levers": levers},
             child=True)
        return

    levers = best_levers(list(statuses.values()))
    lines = [
        f"{day}  "
        f"{fmt_val(totals['kcal'], 'kcal')}kcal "
        f"P{fmt_g(totals['protein_g'])} C{fmt_g(totals['carbs_g'])} "
        f"F{fmt_g(totals['fat_g'])} (sat{fmt_g(totals['satfat_g'])})",
        f"fibre {fmt_g(totals['fibre_g'])}g | sugar {fmt_g(totals['sugar_g'])}g | "
        f"Na {fmt_val(totals['sodium_mg'], 'mg')}mg",
        f"veg {fmt_g(totals['veg_servings'])} | fruit {fmt_g(totals['fruit_servings'])}"
        + (f" | water {fmt_val(totals['water'], 'ml')}ml" if totals['water'] else ""),
    ]
    tgt_line = "; ".join(p for p in (line("kcal"), line("protein")) if p)
    if tgt_line:
        lines.append("vs targets: " + tgt_line)
    sub_line = "; ".join(p for p in (line("fibre"), line("satfat"), line("sodium")) if p)
    if sub_line:
        lines.append("  " + sub_line)
    if levers:
        lines.append("levers: " + ", ".join(levers))
    emit(args, "\n".join(lines[:8]),
         {"person": pkey, "kind": kind, "day": day, "totals": totals,
          "targets": list(statuses.values()), "levers": levers})


def cmd_week(conn, args):
    person = resolve_person(conn, args)
    pkey, kind = person["key"], person["kind"]
    end = datetime.strptime(resolve_day(args.end), "%Y-%m-%d").date()
    days = [(end - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

    if kind == "child":
        fields = ["protein_g", "iron_mg", "calcium_mg", "fibre_g"]
        rows = []
        acc = {f: 0.0 for f in fields}
        acc_vf = acc_milk = 0.0
        for d in days:
            t = day_totals(conn, d, pkey)
            vf = (t["veg_servings"] or 0) + (t["fruit_servings"] or 0)
            rows.append({"day": d, "protein_g": t["protein_g"], "iron_mg": t["iron_mg"],
                         "calcium_mg": t["calcium_mg"], "fibre_g": t["fibre_g"],
                         "vegfruit": vf, "milk_ml": t["milk_ml"]})
            for f in fields:
                acc[f] += t[f]
            acc_vf += vf
            acc_milk += t["milk_ml"]
        avg = {f: acc[f] / 7 for f in fields}
        avg["vegfruit"] = acc_vf / 7
        avg["milk_ml"] = acc_milk / 7
        header = (f"{'day':<12}{'P':>7}{'iron':>7}{'Ca':>7}{'fibre':>7}"
                  f"{'v+f':>7}{'milk':>8}")
        lines = [f"Week ending {end.isoformat()} — {pkey} (child)", header]
        for r in rows:
            lines.append(
                f"{r['day']:<12}{fmt_g(r['protein_g']):>7}{fmt_val(r['iron_mg'],'mg'):>7}"
                f"{fmt_val(r['calcium_mg'],'mg'):>7}{fmt_g(r['fibre_g']):>7}"
                f"{fmt_g(r['vegfruit']):>7}{fmt_val(r['milk_ml'],'ml'):>8}")
        lines.append(
            f"{'avg':<12}{fmt_g(avg['protein_g']):>7}{fmt_val(avg['iron_mg'],'mg'):>7}"
            f"{fmt_val(avg['calcium_mg'],'mg'):>7}{fmt_g(avg['fibre_g']):>7}"
            f"{fmt_g(avg['vegfruit']):>7}{fmt_val(avg['milk_ml'],'ml'):>8}")
        emit(args, "\n".join(lines),
             {"person": pkey, "kind": kind, "end": end.isoformat(),
              "days": rows, "averages": avg}, child=True)
        return

    fields = ["protein_g", "kcal", "fibre_g", "satfat_g"]
    rows = []
    acc = {f: 0.0 for f in fields}
    acc_vf = acc_w = 0.0
    for d in days:
        t = day_totals(conn, d, pkey)
        vf = (t["veg_servings"] or 0) + (t["fruit_servings"] or 0)
        row = {"day": d, "protein_g": t["protein_g"], "kcal": t["kcal"],
               "fibre_g": t["fibre_g"], "satfat_g": t["satfat_g"],
               "vegfruit": vf, "water_ml": t["water"]}
        rows.append(row)
        for f in fields:
            acc[f] += t[f]
        acc_vf += vf
        acc_w += t["water"]
    avg = {f: acc[f] / 7 for f in fields}
    avg["vegfruit"] = acc_vf / 7
    avg["water_ml"] = acc_w / 7

    header = f"{'day':<12}{'P':>7}{'kcal':>7}{'fibre':>7}{'sat':>7}{'v+f':>7}{'water':>8}"
    lines = [f"Week ending {end.isoformat()}", header]
    for r in rows:
        lines.append(
            f"{r['day']:<12}{fmt_g(r['protein_g']):>7}{fmt_val(r['kcal'],'kcal'):>7}"
            f"{fmt_g(r['fibre_g']):>7}{fmt_g(r['satfat_g']):>7}"
            f"{fmt_g(r['vegfruit']):>7}{fmt_val(r['water_ml'],'ml'):>8}")
    lines.append(
        f"{'avg':<12}{fmt_g(avg['protein_g']):>7}{fmt_val(avg['kcal'],'kcal'):>7}"
        f"{fmt_g(avg['fibre_g']):>7}{fmt_g(avg['satfat_g']):>7}"
        f"{fmt_g(avg['vegfruit']):>7}{fmt_val(avg['water_ml'],'ml'):>8}")
    emit(args, "\n".join(lines),
         {"person": pkey, "kind": kind, "end": end.isoformat(),
          "days": rows, "averages": avg})


def cmd_water(conn, args):
    person = resolve_person(conn, args)
    dt = parse_at(args.at)
    day = dt.date().isoformat()
    conn.execute("INSERT INTO water(person,day,ml,at) VALUES (?,?,?,?)",
                 (person["key"], day, args.ml, dt.isoformat()))
    conn.commit()
    total = conn.execute("SELECT COALESCE(SUM(ml),0) FROM water WHERE day=? AND person=?",
                         (day, person["key"])).fetchone()[0]
    emit(args, f"+{fmt_val(args.ml, 'ml')}ml water for {person['key']} "
               f"(day total {fmt_val(total, 'ml')}ml)",
         {"person": person["key"], "added_ml": args.ml, "day": day,
          "day_total_ml": total})


def cmd_targets(conn, args):
    person = resolve_person(conn, args)
    pkey = person["key"]
    if args.op == "set":
        if not args.key or args.value is None:
            raise UserError("targets set KEY VALUE [--kind ..]")
        existing = conn.execute("SELECT * FROM targets WHERE person=? AND key=?",
                                (pkey, args.key)).fetchone()
        kind = args.kind or (existing["kind"] if existing else None)
        if kind is None:
            raise UserError("new target needs --kind (min|max|range_lo|range_hi)")
        unit = existing["unit"] if existing else None
        note = existing["note"] if existing else None
        conn.execute(
            "INSERT INTO targets(person,key,value,kind,unit,note) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(person,key) DO UPDATE SET value=excluded.value, kind=excluded.kind",
            (pkey, args.key, args.value, kind, unit, note))
        conn.commit()
        r = conn.execute("SELECT * FROM targets WHERE person=? AND key=?",
                         (pkey, args.key)).fetchone()
        emit(args, f"set target {pkey}.{args.key} = {args.value} ({kind})",
             entry_to_dict(r))
        return
    targets = get_targets(conn, pkey)
    lines, obj = [], {}
    for name, field, kind, unit in NUTRIENT_TARGETS:
        if kind == "range":
            lo, hi = targets.get(name + "_lo"), targets.get(name + "_hi")
            if lo and hi:
                lines.append(f"{name}: {fmt_val(lo['value'], unit)}–"
                             f"{fmt_val(hi['value'], unit)} {unit}")
                obj[name] = {"kind": "range", "lo": lo["value"], "hi": hi["value"],
                             "unit": unit}
        else:
            row = targets.get(name)
            if row:
                lines.append(f"{name}: {kind} {fmt_val(row['value'], unit)} {unit}")
                obj[name] = {"kind": kind, "value": row["value"], "unit": unit,
                             "note": row["note"]}
    if not obj:
        emit(args, f"(no targets set for {pkey})", {"person": pkey, "targets": {}})
        return
    emit(args, "\n".join(lines), {"person": pkey, "targets": obj})


def cmd_body(conn, args):
    person = resolve_person(conn, args)
    pkey = person["key"]
    if args.op == "add":
        if not args.metric or args.value is None:
            raise UserError("body add METRIC VALUE [--day ..] [--source ..]")
        try:
            value = float(args.value)
        except ValueError:
            raise UserError(f"body value must be a number, got {args.value!r}")
        day = resolve_day(args.day) if args.day else now_dt().date().isoformat()
        at = now_iso()
        conn.execute(
            "INSERT INTO body(person,day,metric,value,source,at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(person,day,metric,source) DO UPDATE SET value=excluded.value, "
            "at=excluded.at",
            (pkey, day, args.metric, value, args.source, at))
        conn.commit()
        emit(args, f"body: {pkey} {args.metric} = {value} on {day} ({args.source})",
             {"person": pkey, "day": day, "metric": args.metric, "value": value,
              "source": args.source})
        return
    # latest
    rows = conn.execute("SELECT * FROM body WHERE person=?", (pkey,)).fetchall()
    latest = {}
    for r in rows:
        if args.metric and r["metric"] != args.metric:
            continue
        cur = latest.get(r["metric"])
        if cur is None or (r["day"], r["at"] or "") > (cur["day"], cur["at"] or ""):
            latest[r["metric"]] = r
    out = {m: {"value": r["value"], "day": r["day"], "source": r["source"]}
           for m, r in latest.items()}
    lines = [f"{m}: {r['value']} ({r['day']}, {r['source']})"
             for m, r in sorted(latest.items())]
    emit(args, "\n".join(lines) if lines else "(no body metrics)", out)


def cmd_export(conn, args):
    person = resolve_person(conn, args)
    q = "SELECT * FROM entries WHERE person=?"
    params = [person["key"]]
    if args.from_d:
        q += " AND day>=?"
        params.append(resolve_day(args.from_d))
    if args.to_d:
        q += " AND day<=?"
        params.append(resolve_day(args.to_d))
    q += " ORDER BY eaten_at, id"
    rows = [entry_to_dict(r) for r in conn.execute(q, params).fetchall()]
    print(json.dumps(rows, default=str, indent=None if args.json else 2))


def cmd_people_day(conn, args):
    day = resolve_day(args.day)
    persons = conn.execute(
        "SELECT DISTINCT person FROM entries WHERE day=? ORDER BY person",
        (day,)).fetchall()
    lines = []
    out = []
    for pr in persons:
        pkey = pr["person"]
        prow = get_person(conn, pkey)
        kind = prow["kind"] if prow else "adult"
        totals = day_totals(conn, day, pkey)
        n = conn.execute("SELECT COUNT(*) FROM entries WHERE day=? AND person=?",
                         (day, pkey)).fetchone()[0]
        if kind == "child":
            line = (f"{pkey:<9} {n:>2} items  P{fmt_g(totals['protein_g'])}g "
                    f"Fe{fmt_total(totals, 'iron_mg', 'mg')}mg "
                    f"Ca{fmt_total(totals, 'calcium_mg', 'mg')}mg "
                    f"fib{fmt_g(totals['fibre_g'])} v{fmt_g(totals['veg_servings'])} "
                    f"f{fmt_g(totals['fruit_servings'])}")
            info = {"person": pkey, "kind": kind, "entries": n,
                    "protein_g": totals["protein_g"], "iron_mg": totals["iron_mg"],
                    "calcium_mg": totals["calcium_mg"], "fibre_g": totals["fibre_g"],
                    "veg_servings": totals["veg_servings"],
                    "fruit_servings": totals["fruit_servings"],
                    "milk_ml": totals["milk_ml"]}
            info = strip_child_keys(info)  # defensive: never leak adult keys
        else:
            line = (f"{pkey:<9} {n:>2} items  {fmt_val(totals['kcal'],'kcal')}kcal "
                    f"P{fmt_g(totals['protein_g'])}g fib{fmt_g(totals['fibre_g'])} "
                    f"v{fmt_g(totals['veg_servings'])} f{fmt_g(totals['fruit_servings'])}")
            info = {"person": pkey, "kind": kind, "entries": n,
                    "kcal": totals["kcal"], "protein_g": totals["protein_g"],
                    "fibre_g": totals["fibre_g"],
                    "veg_servings": totals["veg_servings"],
                    "fruit_servings": totals["fruit_servings"]}
        lines.append(line)
        out.append(info)
    emit(args, "\n".join(lines) if lines else f"(no entries for {day})",
         {"day": day, "people": out})


def cmd_gaps(conn, args):
    n = args.days
    today = now_dt().date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(n)]
    forced = getattr(args, "person", None) or os.environ.get("NUTRITION_PERSON")
    if forced:
        persons = [resolve_person(conn, args)]
    else:
        persons = conn.execute(
            "SELECT * FROM people WHERE kind='child' ORDER BY key").fetchall()

    results = []
    for p in persons:
        pkey, kind = p["key"], p["kind"]
        logged_days = 0
        miss = {}   # nutrient -> {count, status detail}
        for d in days:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE day=? AND person=?",
                (d, pkey)).fetchone()[0]
            if not cnt:
                continue  # no data that day -> not a real "miss"
            logged_days += 1
            totals = day_totals(conn, d, pkey)
            for s in target_statuses(conn, totals, pkey):
                if kind == "child" and s["nutrient"] not in CHILD_TARGET_NAMES:
                    continue
                if s["state"] in MISS_STATES:
                    rec = miss.setdefault(
                        s["nutrient"],
                        {"nutrient": s["nutrient"], "kind": s["kind"],
                         "unit": s["unit"], "missed_days": 0,
                         "target": s.get("target") or s.get("lo")})
                    rec["missed_days"] += 1
        gaps = [v for v in miss.values() if v["missed_days"] >= 2]
        gaps.sort(key=lambda g: (-g["missed_days"], g["nutrient"]))
        if logged_days < 2:
            # Too thin to tell on-track from gaps; don't guess either way.
            status, on_track = "insufficient_data", None
        else:
            status = "gaps" if gaps else "on_track"
            on_track = not gaps
        results.append({"person": pkey, "logged_days": logged_days,
                        "status": status, "on_track": on_track, "gaps": gaps})

    if getattr(args, "json", False):
        print(json.dumps(
            {"day": today.isoformat(), "days_checked": n, "people": results},
            default=str))
    else:
        lines = []
        for r in results:
            if r["status"] == "insufficient_data":
                d = r["logged_days"]
                lines.append(f"{r['person']}: not enough data yet "
                             f"({d} logged day{'' if d == 1 else 's'})")
            elif not r["gaps"]:
                lines.append(f"{r['person']}: on track ({r['logged_days']} logged days)")
            else:
                g = "; ".join(
                    f"{x['nutrient']} missed {x['missed_days']}/{r['logged_days']} days"
                    for x in r["gaps"])
                lines.append(f"{r['person']}: {g}")
        print("\n".join(lines) if lines else "(no children to check)")


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--person", help="who this is for (default NUTRITION_PERSON or sumeet)")

    p = argparse.ArgumentParser(prog="nutrition.py",
                                description="household food + nutrient tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", parents=[common], help="create/upgrade schema, seed people+targets+foods")

    # person
    pp = sub.add_parser("person", parents=[common], help="manage people")
    psub = pp.add_subparsers(dest="person_cmd", required=True)
    psub.add_parser("list", parents=[common])
    pa = psub.add_parser("add", parents=[common])
    pa.add_argument("--key", required=True)
    pa.add_argument("--name", required=True)
    pa.add_argument("--kind", required=True, choices=["adult", "child"])
    pa.add_argument("--birthday")
    pa.add_argument("--sex")
    pa.add_argument("--notes")
    pe = psub.add_parser("edit", parents=[common])
    pe.add_argument("key")
    pe.add_argument("--name")
    pe.add_argument("--kind", choices=["adult", "child"])
    pe.add_argument("--birthday")
    pe.add_argument("--sex")
    pe.add_argument("--notes")

    # food
    fp = sub.add_parser("food", parents=[common], help="manage the food table")
    fsub = fp.add_subparsers(dest="food_cmd", required=True)
    fa = fsub.add_parser("add", parents=[common])
    fa.add_argument("--key", required=True)
    fa.add_argument("--name", required=True)
    fa.add_argument("--basis", required=True, choices=["100g", "serving"])
    fa.add_argument("--serving-g", dest="serving_g", type=float)
    fa.add_argument("--unit")
    for nm in ("kcal", "protein", "carbs", "fat", "satfat", "fibre", "sugar",
               "sodium", "iron", "calcium", "veg", "fruit"):
        fa.add_argument(f"--{nm}", type=float)
    fa.add_argument("--aliases")
    fa.add_argument("--source")
    fa.add_argument("--notes")
    ff = fsub.add_parser("find", parents=[common])
    ff.add_argument("query")
    fsh = fsub.add_parser("show", parents=[common])
    fsh.add_argument("key")
    fe = fsub.add_parser("edit", parents=[common])
    fe.add_argument("key")
    fe.add_argument("--name")
    fe.add_argument("--basis", choices=["100g", "serving"])
    fe.add_argument("--serving-g", dest="serving_g", type=float)
    fe.add_argument("--unit")
    for nm in ("kcal", "protein", "carbs", "fat", "satfat", "fibre", "sugar",
               "sodium", "iron", "calcium", "veg", "fruit"):
        fe.add_argument(f"--{nm}", type=float)
    fe.add_argument("--aliases")
    fe.add_argument("--source")
    fe.add_argument("--notes")
    frm = fsub.add_parser("rm", parents=[common])
    frm.add_argument("key")
    frm.add_argument("--force", action="store_true")

    # log
    lp = sub.add_parser("log", parents=[common], help="log a food")
    lp.add_argument("food")
    lp.add_argument("qty", type=float)
    lp.add_argument("unit", nargs="?")
    lp.add_argument("--meal")
    lp.add_argument("--at", default="now")
    lp.add_argument("--desc")
    lp.add_argument("--packed", action="store_true", help="packed, not yet eaten")
    lp.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    lp.add_argument("--source", default="hermes")
    lp.add_argument("--logged-by", dest="logged_by")
    lp.add_argument("--reported-by", dest="reported_by")
    lp.add_argument("--force", action="store_true", help="log even if a duplicate is found")
    lp.add_argument("--notes")

    # log-custom
    lc = sub.add_parser("log-custom", parents=[common], help="ad-hoc entry, no food row")
    lc.add_argument("--desc", required=True)
    lc.add_argument("--protein", type=float, required=True)
    for nm in ("kcal", "carbs", "fat", "satfat", "fibre", "sugar", "sodium",
               "iron", "calcium", "veg", "fruit"):
        lc.add_argument(f"--{nm}", type=float)
    lc.add_argument("--meal")
    lc.add_argument("--at", default="now")
    lc.add_argument("--packed", action="store_true", help="packed, not yet eaten")
    lc.add_argument("--confidence", default="low", choices=["high", "medium", "low"])
    lc.add_argument("--source", default="hermes")
    lc.add_argument("--logged-by", dest="logged_by")
    lc.add_argument("--reported-by", dest="reported_by")
    lc.add_argument("--force", action="store_true", help="log even if a duplicate is found")
    lc.add_argument("--notes")

    # edit
    ep = sub.add_parser("edit", parents=[common], help="edit an entry")
    ep.add_argument("id", type=int)
    ep.add_argument("--qty", type=float)
    ep.add_argument("--unit")
    ep.add_argument("--meal")
    ep.add_argument("--at")
    ep.add_argument("--desc")
    ep.add_argument("--notes")
    ep.add_argument("--logged-by", dest="logged_by")
    ep.add_argument("--reported-by", dest="reported_by")
    ep.add_argument("--confidence", choices=["high", "medium", "low"])

    # eaten (adjust after pickup)
    etp = sub.add_parser("eaten", parents=[common], help="adjust how much was eaten")
    etp.add_argument("id", type=int)
    etp.add_argument("--fraction", type=float)
    etp.add_argument("--all", action="store_true")
    etp.add_argument("--none", action="store_true")
    etp.add_argument("--note")

    rp = sub.add_parser("rm", parents=[common], help="delete entries")
    rp.add_argument("ids", nargs="+", type=int)

    dp = sub.add_parser("day", parents=[common], help="list a day + targets")
    dp.add_argument("day", nargs="?", default="today")

    smp = sub.add_parser("summary", parents=[common], help="compact chat block")
    smp.add_argument("day", nargs="?", default="today")

    wp = sub.add_parser("week", parents=[common], help="7-day table")
    wp.add_argument("--end", default="today")

    wtr = sub.add_parser("water", parents=[common], help="log water")
    wtr.add_argument("ml", type=float)
    wtr.add_argument("--at", default="now")

    tp = sub.add_parser("targets", parents=[common], help="show / set targets")
    tp.add_argument("op", nargs="?", choices=["set"])
    tp.add_argument("key", nargs="?")
    tp.add_argument("value", nargs="?", type=float)
    tp.add_argument("--kind", choices=["min", "max", "range_lo", "range_hi"])

    bp = sub.add_parser("body", parents=[common], help="body metrics")
    bp.add_argument("op", choices=["add", "latest"])
    bp.add_argument("metric", nargs="?")
    bp.add_argument("value", nargs="?")
    bp.add_argument("--day")
    bp.add_argument("--source", default="manual")

    xp = sub.add_parser("export", parents=[common], help="dump entries as JSON")
    xp.add_argument("--from", dest="from_d")
    xp.add_argument("--to", dest="to_d")

    pdp = sub.add_parser("people-day", parents=[common],
                         help="one line per person with entries that day")
    pdp.add_argument("day", nargs="?", default="today")

    gp = sub.add_parser("gaps", parents=[common],
                        help="children's repeated target misses over N days")
    gp.add_argument("--days", type=int, default=3)

    return p


DISPATCH = {
    "init": cmd_init, "person": cmd_person, "food": cmd_food, "log": cmd_log,
    "log-custom": cmd_log_custom, "edit": cmd_edit, "eaten": cmd_eaten,
    "rm": cmd_rm, "day": cmd_day, "summary": cmd_summary, "week": cmd_week,
    "water": cmd_water, "targets": cmd_targets, "body": cmd_body,
    "export": cmd_export, "people-day": cmd_people_day, "gaps": cmd_gaps,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    conn = connect()
    try:
        rc = DISPATCH[args.cmd](conn, args)
    except UserError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main())
