#!/usr/bin/env python3
"""Compact chat card for a person's day: icon, group, numbers, then a 10-cell bar (Sumeet's format, 2026-10-14).

  nutcard.py [person] [YYYY-MM-DD|today|yesterday]

Reads the real household DB via `nut day <date> --person P --json` (same code path as MCP `day`).
Min targets fill toward the goal (✅ when hit). Max limits fill toward the cap (⚠️ when over).
"""
import json, subprocess, sys

person = sys.argv[1] if len(sys.argv) > 1 else "sumeet"
day = sys.argv[2] if len(sys.argv) > 2 else "today"
r = subprocess.run([f"{__import__('os').path.expanduser('~')}/.local/bin/nut", "day", day, "--person", person, "--json"],
                   capture_output=True, text=True)
d = json.loads(r.stdout)
T = {t["nutrient"]: t for t in d["targets"]}

ROWS = [  # nutrient key, emoji, label, unit, show_always
    ("protein", "💪", "Protein", "g", True),
    ("kcal", "🔥", "Calories", "", True),
    ("fibre", "🌾", "Fibre", "g", True),
    ("veg_servings", "🥦", "Veg", "", True),
    ("fruit_servings", "🍊", "Fruit", "", True),
    ("satfat", "🧈", "Sat fat", "g", True),
    ("sodium", "🧂", "Sodium", "mg", False),
    # sugar left out on purpose: the DB counts fruit/milk sugar, which Sumeet's limit ignores, so the row would mislead
]


def bar(frac, cells=10):
    n = max(0, min(cells, round(frac * cells)))
    return "▓" * n + "░" * (cells - n)


def num(x):
    return f"{x:,.0f}" if x >= 10 else (f"{x:.1f}".rstrip("0").rstrip(".") or "0")


lines = []
for key, emo, label, unit, always in ROWS:
    t = T.get(key)
    if not t:
        continue
    tot = t["total"]
    goal = t.get("target") or t.get("lo")
    if t["kind"] == "max":
        over = tot > goal
        if not always and not over:
            continue
        mark = " ⚠️" if over else ""
    else:
        mark = " ✅" if tot >= goal else ""
    frac = tot / goal if goal else 0
    lines.append(f"{emo} {label} {num(tot)}/{num(goal)}{unit} {bar(frac)}{mark}")
print("\n".join(lines))
