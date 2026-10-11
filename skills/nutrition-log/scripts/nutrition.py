#!/usr/bin/env python3
"""nutrition.py — Sumeet's food + nutrient tracker (SQLite + CLI, stdlib only).

Hermes (the only user) calls this many times a day to log food, compute
nutrients from a local food table, and see "today vs targets".

DB: env NUTRITION_DB else ~/.hermes/data/nutrition.db (WAL mode).

Common usage:
  nutrition.py init
  nutrition.py log egg 2 eggs --meal breakfast --at now
  nutrition.py log chicken_breast 200 g --meal lunch
  nutrition.py log whey_scoop 1 scoop --meal post-gym
  nutrition.py log-custom --desc "butter chicken (restaurant)" --protein 35 --kcal 650
  nutrition.py day today
  nutrition.py summary
  nutrition.py week
  nutrition.py water 500
  nutrition.py targets
  nutrition.py body add weight_kg 80.2 --source withings
  nutrition.py export --from 2026-10-01 --to 2026-10-11

Every command supports --json for compact machine output.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover - zoneinfo always present on 3.9+
    TZ = None

SCHEMA_VERSION = "1"

# Nutrient columns scaled from the food table into each entry snapshot.
FOOD_NUTRIENTS = [
    "kcal", "protein_g", "carbs_g", "fat_g", "satfat_g",
    "fibre_g", "sugar_g", "sodium_mg", "veg_servings", "fruit_servings",
]

FOOD_COLS = [
    "key", "name", "aliases", "basis", "serving_g", "unit_name",
    "kcal", "protein_g", "carbs_g", "fat_g", "satfat_g", "fibre_g",
    "sugar_g", "sodium_mg", "veg_servings", "fruit_servings",
    "source", "notes", "updated_at",
]

ENTRY_COLS = [
    "eaten_at", "day", "meal", "food_id", "description", "qty", "qty_unit",
    "grams", "kcal", "protein_g", "carbs_g", "fat_g", "satfat_g", "fibre_g",
    "sugar_g", "sodium_mg", "veg_servings", "fruit_servings",
    "confidence", "source", "notes", "created_at", "updated_at",
]

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
    ("veg_servings", "veg_servings", "min", "srv"),
    ("fruit_servings", "fruit_servings", "min", "srv"),
    ("water_ml", "water", "min", "ml"),
]

# (key, value, kind, unit, note) seeded idempotently on init.
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
    ("water_ml", 3000, "min", "ml", None),
]

DISP_NAME = {"veg_servings": "veg", "fruit_servings": "fruit", "water_ml": "water"}


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


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS foods(
          id INTEGER PRIMARY KEY,
          key TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          aliases TEXT DEFAULT '',
          basis TEXT NOT NULL CHECK(basis IN ('100g','serving')),
          serving_g REAL,
          unit_name TEXT,
          kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL, satfat_g REAL,
          fibre_g REAL, sugar_g REAL, sodium_mg REAL,
          veg_servings REAL DEFAULT 0, fruit_servings REAL DEFAULT 0,
          source TEXT, notes TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS entries(
          id INTEGER PRIMARY KEY,
          eaten_at TEXT NOT NULL,
          day TEXT NOT NULL,
          meal TEXT,
          food_id INTEGER REFERENCES foods(id),
          description TEXT NOT NULL,
          qty REAL NOT NULL,
          qty_unit TEXT NOT NULL,
          grams REAL,
          kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL, satfat_g REAL,
          fibre_g REAL, sugar_g REAL, sodium_mg REAL,
          veg_servings REAL, fruit_servings REAL,
          confidence TEXT DEFAULT 'medium',
          source TEXT, notes TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_entries_day ON entries(day);
        CREATE TABLE IF NOT EXISTS water(
          id INTEGER PRIMARY KEY, day TEXT, ml REAL, at TEXT
        );
        CREATE TABLE IF NOT EXISTS targets(
          key TEXT PRIMARY KEY,
          value REAL,
          kind TEXT CHECK(kind IN ('min','max','range_lo','range_hi')),
          unit TEXT, note TEXT
        );
        CREATE TABLE IF NOT EXISTS body(
          id INTEGER PRIMARY KEY, day TEXT, metric TEXT, value REAL,
          source TEXT, at TEXT, UNIQUE(day,metric,source)
        );
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        """
    )
    conn.commit()


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
def norm_unit(food, raw):
    """Return canonical token: 'g', 'serving', or the food's unit_name."""
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
    if u in ("unit", "units"):
        return food["unit_name"] or "serving"
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


def entry_to_dict(r):
    return {k: r[k] for k in r.keys()}


def day_totals(conn, day):
    totals = {f: 0.0 for f in FOOD_NUTRIENTS}
    for r in conn.execute("SELECT * FROM entries WHERE day=?", (day,)).fetchall():
        for f in FOOD_NUTRIENTS:
            totals[f] += r[f] or 0.0
    water = conn.execute(
        "SELECT COALESCE(SUM(ml),0) FROM water WHERE day=?", (day,)).fetchone()[0]
    totals["water"] = water or 0.0
    return totals


# --------------------------------------------------------------------------- #
# targets
# --------------------------------------------------------------------------- #
def get_targets(conn):
    return {r["key"]: r for r in conn.execute("SELECT * FROM targets").fetchall()}


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


def target_statuses(conn, totals):
    targets = get_targets(conn)
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


# --------------------------------------------------------------------------- #
# output helper
# --------------------------------------------------------------------------- #
def emit(args, human, obj):
    if getattr(args, "json", False):
        print(json.dumps(obj, default=str))
    else:
        print(human)


# --------------------------------------------------------------------------- #
# command handlers
# --------------------------------------------------------------------------- #
def cmd_init(conn, args):
    for key, value, kind, unit, note in SEED_TARGETS:
        conn.execute(
            "INSERT OR IGNORE INTO targets(key,value,kind,unit,note) VALUES (?,?,?,?,?)",
            (key, value, kind, unit, note))
    conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES ('schema_version',?)",
                 (SCHEMA_VERSION,))
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
    emit(args, f"initialized db at {db_path()} — {nfoods} foods, "
               f"{len(SEED_TARGETS)} target rows (loaded {loaded} seed foods)",
         {"db": str(db_path()), "foods": nfoods, "seed_loaded": loaded})


def _food_data_from_args(args):
    data = {}
    mapping = {
        "name": "name", "basis": "basis", "serving_g": "serving_g",
        "unit": "unit_name", "kcal": "kcal", "protein": "protein_g",
        "carbs": "carbs_g", "fat": "fat_g", "satfat": "satfat_g",
        "fibre": "fibre_g", "sugar": "sugar_g", "sodium": "sodium_mg",
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
                         "protein_g": m["protein_g"], "kcal": m["kcal"]})
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


def cmd_log(conn, args):
    food = require_food(conn, args.food)
    token = norm_unit(food, args.unit)
    snap, grams, servings = compute_snapshot(food, args.qty, token)
    dt = parse_at(args.at)
    desc = args.desc or food["name"]
    row = {
        "eaten_at": dt.isoformat(), "day": dt.date().isoformat(),
        "meal": args.meal, "food_id": food["id"], "description": desc,
        "qty": args.qty, "qty_unit": token, "grams": grams,
        "confidence": args.confidence, "source": args.source,
        "notes": args.notes, "created_at": now_iso(), "updated_at": now_iso(),
    }
    row.update(snap)
    eid = insert_entry(conn, row)
    r = get_entry(conn, eid)
    _emit_logged(args, r, conn)


def cmd_log_custom(conn, args):
    dt = parse_at(args.at)
    row = {
        "eaten_at": dt.isoformat(), "day": dt.date().isoformat(),
        "meal": args.meal, "food_id": None, "description": args.desc,
        "qty": 1, "qty_unit": "serving", "grams": None,
        "confidence": args.confidence, "source": args.source,
        "notes": args.notes, "created_at": now_iso(), "updated_at": now_iso(),
    }
    for f in FOOD_NUTRIENTS:
        row[f] = None
    mapping = {"kcal": "kcal", "protein": "protein_g", "carbs": "carbs_g",
               "fat": "fat_g", "satfat": "satfat_g", "fibre": "fibre_g",
               "sugar": "sugar_g", "sodium": "sodium_mg", "veg": "veg_servings",
               "fruit": "fruit_servings"}
    for a, col in mapping.items():
        v = getattr(args, a, None)
        if v is not None:
            row[col] = v
    eid = insert_entry(conn, row)
    r = get_entry(conn, eid)
    _emit_logged(args, r, conn)


def _emit_logged(args, r, conn):
    totals = day_totals(conn, r["day"])
    human = (f"logged #{r['id']} {r['description']} "
             f"{fmt_qty(r['qty'])} {r['qty_unit']} → "
             f"P {fmt_g(r['protein_g'])}g, {fmt_val(r['kcal'], 'kcal')} kcal"
             f"  [day: P {fmt_g(totals['protein_g'])}g / "
             f"{fmt_val(totals['kcal'], 'kcal')} kcal]")
    emit(args, human, entry_to_dict(r))


def cmd_edit(conn, args):
    r = get_entry(conn, args.id)
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


def cmd_rm(conn, args):
    removed = []
    for eid in args.ids:
        get_entry(conn, eid)  # raises if missing
        conn.execute("DELETE FROM entries WHERE id=?", (eid,))
        removed.append(eid)
    conn.commit()
    emit(args, f"deleted {len(removed)} entr{'y' if len(removed) == 1 else 'ies'}: "
               + ", ".join(f"#{e}" for e in removed),
         {"deleted": removed})


def cmd_day(conn, args):
    day = resolve_day(args.day)
    entries = conn.execute(
        "SELECT * FROM entries WHERE day=? ORDER BY eaten_at, id", (day,)).fetchall()
    totals = day_totals(conn, day)
    statuses = target_statuses(conn, totals)
    levers = best_levers(statuses)

    elist = []
    lines = [f"Day {day}"]
    for e in entries:
        t = e["eaten_at"][11:16] if e["eaten_at"] else "--:--"
        lines.append(
            f"  #{e['id']} {t} {e['meal'] or '-':<9} {e['description']} "
            f"[{fmt_qty(e['qty'])} {e['qty_unit']}] "
            f"P{fmt_g(e['protein_g'])} {fmt_val(e['kcal'], 'kcal')}kcal "
            f"Fib{fmt_g(e['fibre_g'])}")
        elist.append(entry_to_dict(e))
    if not entries:
        lines.append("  (no entries)")
    lines.append(
        f"Totals: {fmt_val(totals['kcal'], 'kcal')} kcal, "
        f"P {fmt_g(totals['protein_g'])}g, C {fmt_g(totals['carbs_g'])}g, "
        f"Fat {fmt_g(totals['fat_g'])}g, Sat {fmt_g(totals['satfat_g'])}g, "
        f"Fib {fmt_g(totals['fibre_g'])}g, Sug {fmt_g(totals['sugar_g'])}g, "
        f"Na {fmt_val(totals['sodium_mg'], 'mg')}mg, "
        f"veg {fmt_g(totals['veg_servings'])}, fruit {fmt_g(totals['fruit_servings'])}, "
        f"water {fmt_val(totals['water'], 'ml')}ml")
    lines.append("Targets:")
    for s in statuses:
        lines.append(f"  {s['nutrient']}: {fmt_val(s['total'], s['unit'])}{s['unit']} "
                     f"{s['status']}")
    if levers:
        lines.append("Next best levers: " + ", ".join(levers))
    emit(args, "\n".join(lines),
         {"day": day, "entries": elist, "totals": totals,
          "targets": statuses, "levers": levers})


def cmd_summary(conn, args):
    day = resolve_day(args.day)
    totals = day_totals(conn, day)
    statuses = {s["nutrient"]: s for s in target_statuses(conn, totals)}
    levers = best_levers(list(statuses.values()))

    def line(nut):
        s = statuses[nut]
        return f"{nut} {fmt_val(s['total'], s['unit'])}{s['unit']} {s['status']}"

    lines = [
        f"{day}  "
        f"{fmt_val(totals['kcal'], 'kcal')}kcal "
        f"P{fmt_g(totals['protein_g'])} C{fmt_g(totals['carbs_g'])} "
        f"F{fmt_g(totals['fat_g'])} (sat{fmt_g(totals['satfat_g'])})",
        f"fibre {fmt_g(totals['fibre_g'])}g | sugar {fmt_g(totals['sugar_g'])}g | "
        f"Na {fmt_val(totals['sodium_mg'], 'mg')}mg",
        f"veg {fmt_g(totals['veg_servings'])} | fruit {fmt_g(totals['fruit_servings'])} | "
        f"water {fmt_val(totals['water'], 'ml')}ml",
        "vs targets: " + line("kcal") + "; " + line("protein"),
        "  " + line("fibre") + "; " + line("satfat") + "; " + line("sodium"),
    ]
    if levers:
        lines.append("levers: " + ", ".join(levers))
    emit(args, "\n".join(lines[:8]),
         {"day": day, "totals": totals,
          "targets": list(statuses.values()), "levers": levers})


def cmd_week(conn, args):
    end = datetime.strptime(resolve_day(args.end), "%Y-%m-%d").date()
    days = [(end - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    fields = ["protein_g", "kcal", "fibre_g", "satfat_g"]
    rows = []
    acc = {f: 0.0 for f in fields}
    acc_vf = acc_w = 0.0
    for d in days:
        t = day_totals(conn, d)
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
    emit(args, "\n".join(lines), {"end": end.isoformat(), "days": rows, "averages": avg})


def cmd_water(conn, args):
    dt = parse_at(args.at)
    conn.execute("INSERT INTO water(day,ml,at) VALUES (?,?,?)",
                 (dt.date().isoformat(), args.ml, dt.isoformat()))
    conn.commit()
    total = conn.execute("SELECT COALESCE(SUM(ml),0) FROM water WHERE day=?",
                         (dt.date().isoformat(),)).fetchone()[0]
    emit(args, f"+{fmt_val(args.ml, 'ml')}ml water "
               f"(day total {fmt_val(total, 'ml')}ml)",
         {"added_ml": args.ml, "day": dt.date().isoformat(), "day_total_ml": total})


def cmd_targets(conn, args):
    if args.op == "set":
        if not args.key or args.value is None:
            raise UserError("targets set KEY VALUE [--kind ..]")
        existing = conn.execute("SELECT * FROM targets WHERE key=?",
                                (args.key,)).fetchone()
        kind = args.kind or (existing["kind"] if existing else None)
        if kind is None:
            raise UserError("new target needs --kind (min|max|range_lo|range_hi)")
        unit = existing["unit"] if existing else None
        note = existing["note"] if existing else None
        conn.execute(
            "INSERT INTO targets(key,value,kind,unit,note) VALUES (?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, kind=excluded.kind",
            (args.key, args.value, kind, unit, note))
        conn.commit()
        r = conn.execute("SELECT * FROM targets WHERE key=?", (args.key,)).fetchone()
        emit(args, f"set target {args.key} = {args.value} ({kind})", entry_to_dict(r))
        return
    targets = get_targets(conn)
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
    emit(args, "\n".join(lines), obj)


def cmd_body(conn, args):
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
            "INSERT INTO body(day,metric,value,source,at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(day,metric,source) DO UPDATE SET value=excluded.value, "
            "at=excluded.at",
            (day, args.metric, value, args.source, at))
        conn.commit()
        emit(args, f"body: {args.metric} = {value} on {day} ({args.source})",
             {"day": day, "metric": args.metric, "value": value, "source": args.source})
        return
    # latest
    rows = conn.execute("SELECT * FROM body").fetchall()
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
    q, params = "SELECT * FROM entries", []
    conds = []
    if args.from_d:
        conds.append("day>=?")
        params.append(resolve_day(args.from_d))
    if args.to_d:
        conds.append("day<=?")
        params.append(resolve_day(args.to_d))
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY eaten_at, id"
    rows = [entry_to_dict(r) for r in conn.execute(q, params).fetchall()]
    print(json.dumps(rows, default=str, indent=None if args.json else 2))


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")

    p = argparse.ArgumentParser(prog="nutrition.py",
                                description="Sumeet's food + nutrient tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", parents=[common], help="create schema, seed targets+foods")

    # food
    fp = sub.add_parser("food", parents=[common], help="manage the food table")
    fsub = fp.add_subparsers(dest="food_cmd", required=True)
    fa = fsub.add_parser("add", parents=[common])
    fa.add_argument("--key", required=True)
    fa.add_argument("--name", required=True)
    fa.add_argument("--basis", required=True, choices=["100g", "serving"])
    fa.add_argument("--serving-g", dest="serving_g", type=float)
    fa.add_argument("--unit")
    for n in ("kcal", "protein", "carbs", "fat", "satfat", "fibre", "sugar",
              "sodium", "veg", "fruit"):
        fa.add_argument(f"--{n}", type=float)
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
    for n in ("kcal", "protein", "carbs", "fat", "satfat", "fibre", "sugar",
              "sodium", "veg", "fruit"):
        fe.add_argument(f"--{n}", type=float)
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
    lp.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    lp.add_argument("--source", default="hermes")
    lp.add_argument("--notes")

    # log-custom
    lc = sub.add_parser("log-custom", parents=[common], help="ad-hoc entry, no food row")
    lc.add_argument("--desc", required=True)
    lc.add_argument("--protein", type=float, required=True)
    for n in ("kcal", "carbs", "fat", "satfat", "fibre", "sugar", "sodium",
              "veg", "fruit"):
        lc.add_argument(f"--{n}", type=float)
    lc.add_argument("--meal")
    lc.add_argument("--at", default="now")
    lc.add_argument("--confidence", default="low", choices=["high", "medium", "low"])
    lc.add_argument("--source", default="hermes")
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
    ep.add_argument("--confidence", choices=["high", "medium", "low"])

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

    return p


DISPATCH = {
    "init": cmd_init, "food": cmd_food, "log": cmd_log, "log-custom": cmd_log_custom,
    "edit": cmd_edit, "rm": cmd_rm, "day": cmd_day, "summary": cmd_summary,
    "week": cmd_week, "water": cmd_water, "targets": cmd_targets, "body": cmd_body,
    "export": cmd_export,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    conn = connect()
    try:
        DISPATCH[args.cmd](conn, args)
    except UserError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
