#!/usr/bin/env python3
"""Compact chat card for a person's day: one aligned monospace block (Sumeet's choice "E", 2026-10-15).

  nutcard.py [person] [YYYY-MM-DD|today|yesterday]

Prints a ``` code block, so Telegram renders it in a fixed-width font and every column lines up:
  Protein   ████▌░░░░░   44%    62/140g
Bars use 1/8-block glyphs for half steps. Min targets fill toward the goal (✓ when hit). Max limits fill
toward the cap (⚠ when over). Reads the real household DB via `nut day <date> --person P --json`
(same code path as MCP `day`).
"""
import json, os, subprocess, sys

person = sys.argv[1] if len(sys.argv) > 1 else "sumeet"
day = sys.argv[2] if len(sys.argv) > 2 else "today"
r = subprocess.run([os.path.expanduser("~/.local/bin/nut"), "day", day, "--person", person, "--json"],
                   capture_output=True, text=True)
d = json.loads(r.stdout)
T = {t["nutrient"]: t for t in d["targets"]}

ROWS = [  # nutrient key, label, unit, show_always
    ("protein", "Protein", "g", True),
    ("kcal", "Calories", "", True),
    ("fibre", "Fibre", "g", True),
    ("veg_servings", "Veg", "", True),
    ("fruit_servings", "Fruit", "", True),
    ("satfat", "Sat fat", "g", True),
    ("sodium", "Sodium", "mg", False),
    # sugar left out on purpose: the DB counts fruit/milk sugar, which Sumeet's limit ignores, so the row would mislead
]

def bar(frac, cells=10):
    frac = max(0.0, min(1.0, frac))
    half = round(frac * cells * 2)  # half-cell resolution
    full, rem = divmod(half, 2)
    return "█" * full + ("▌" if rem else "") + "░" * (cells - full - rem)

def num(x):
    return f"{x:,.0f}" if x >= 10 else (f"{x:.1f}".rstrip("0").rstrip(".") or "0")

rows = []
for key, label, unit, always in ROWS:
    t = T.get(key)
    if not t:
        continue
    tot = t["total"]
    goal = t.get("target") or t.get("lo")
    if t["kind"] == "max":
        over = tot > goal
        if not always and not over:
            continue
        mark = "⚠" if over else ""
    else:
        mark = "✓" if tot >= goal else ""
    frac = tot / goal if goal else 0
    pct = f"{round(frac * 100)}%"
    rows.append((label, bar(frac), pct, f"{num(tot)}/{num(goal)}{unit}", mark))

lw = max(len(r[0]) for r in rows)
out = [f"{l:<{lw}}  {b}  {p:>4}  {n}{(' ' + m) if m else ''}" for l, b, p, n, m in rows]
print("```\n" + "\n".join(out) + "\n```")
