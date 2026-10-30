#!/usr/bin/env python3
"""WHO growth percentiles (0-5 y) for kids' weight / length-height / BMI, with outlier flags.

Canada uses the WHO Child Growth Standards for 0-5 y (Dietitians of Canada + CPS + CFPC + CHNC + CPEG,
"WHO Growth Charts for Canada", 2014). Tables: who_lms_0_5.json next to this script (monthly LMS).

Usage:
  growth_percentiles.py point  --sex boy --dob 2025-01-31 --date 2026-10-28 --kg 11.2 --cm 84.4 [--method lying|standing]
  growth_percentiles.py series --sex boy --dob 2025-01-31 --csv measures.csv     # rows: date,kg,cm[,note]  (blank = missing)
  growth_percentiles.py selftest

Rules baked in (sources in the wiki page concepts/kids-growth-tracking.md):
  * Under 24 mo the standard is recumbent LENGTH; 24 mo+ is standing HEIGHT. Standing reads ~0.7 cm less than
    lying. --method says how it was measured; the script converts to the standard's method.
  * WHO screening cut-offs: <3rd centile = underweight / stunted / wasted (BMI); >97th BMI = overweight risk side.
  * Flags: a height LOWER than an earlier one by >1 cm, or a height z jump >1.0 between checks, is almost always a
    measurement error (toddlers resist leg extension). Don't size clothes or worry off a single outlier; re-measure.
"""
import argparse, csv, datetime as dt, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = json.load(open(os.path.join(HERE, "who_lms_0_5.json")))["tables"]
DAYS_PER_MONTH = 30.4375


def _lms(name, m):
    rows = TABLES[name]
    if m < rows[0][0] or m > rows[-1][0]:
        raise ValueError(f"age {m:.1f} mo outside {name} range {rows[0][0]}-{rows[-1][0]}")
    for a, b in zip(rows, rows[1:]):
        if a[0] <= m <= b[0]:
            t = 0 if b[0] == a[0] else (m - a[0]) / (b[0] - a[0])
            return [a[i] + t * (b[i] - a[i]) for i in (1, 2, 3)]
    return rows[-1][1:]


def zscore(v, L, M, S):
    z = math.log(v / M) / S if L == 0 else ((v / M) ** L - 1) / (L * S)
    # WHO restricted-LMS tail adjustment for weight/BMI beyond +-3 SD
    if abs(z) > 3 and L != 1:
        def at(sd): return M * (1 + L * S * sd) ** (1 / L)
        if z > 3:
            sd23 = at(3) - at(2); z = 3 + (v - at(3)) / sd23
        else:
            sd23 = at(-2) - at(-3); z = -3 + (v - at(-3)) / sd23
    return z


def pct(z):
    return 50 * (1 + math.erf(z / math.sqrt(2)))


def months(dob, date):
    return (date - dob).days / DAYS_PER_MONTH


def assess(sex, dob, date, kg=None, cm=None, method=None):
    s = {"boy": "boys", "girl": "girls"}[sex]
    m = months(dob, date)
    out = {"date": date.isoformat(), "age_months": round(m, 1)}
    if kg:
        z = zscore(kg, *_lms(f"{s}_weight", m)); out["weight"] = {"kg": kg, "z": round(z, 2), "pct": round(pct(z))}
    if cm:
        std = "length" if m < 24 else "height"
        adj = cm
        if method == "standing" and std == "length": adj = cm + 0.7
        if method == "lying" and std == "height": adj = cm - 0.7
        z = zscore(adj, *_lms(f"{s}_{std}", m))
        out[std] = {"cm": cm, "used_cm": round(adj, 1), "z": round(z, 2), "pct": round(pct(z))}
        if kg:
            bmi = kg / (adj / 100) ** 2
            z = zscore(bmi, *_lms(f"{s}_bmi_{'0_2' if m < 24 else '2_5'}", m))
            out["bmi"] = {"value": round(bmi, 1), "z": round(z, 2), "pct": round(pct(z))}
    flags = []
    for k, label in (("weight", "underweight"), ("length", "short"), ("height", "short"), ("bmi", "low BMI (wasting screen)")):
        if k in out and out[k]["pct"] < 3: flags.append(f"{k} <3rd centile ({label}): doctor question")
    if "bmi" in out and out["bmi"]["pct"] > 97: flags.append("BMI >97th centile: doctor question")
    out["flags"] = flags
    return out


def series(sex, dob, rows, method=None):
    res, prev = [], None
    for r in rows:
        a = assess(sex, dob, r["date"], r.get("kg"), r.get("cm"), method)
        a["note"] = r.get("note", "")
        lh = a.get("length") or a.get("height")
        if lh and prev:
            if lh["used_cm"] < prev["used_cm"] - 1.0:
                a["flags"].append(f"height {lh['cm']} < earlier {prev['cm']} ({prev['date']}): one of them is a mismeasure")
            if abs(lh["z"] - prev["z"]) > 1.0:
                a["flags"].append(f"height z jumped {prev['z']:+.2f} -> {lh['z']:+.2f}: likely measurement error, re-measure")
        if any("height" in f for f in a["flags"]):
            a["flags"] = [f + " (computed from the suspect height; ignore)" if f.startswith("bmi") else f
                          for f in a["flags"]]
        if lh: prev = dict(lh, date=a["date"])
        res.append(a)
    return res


def fmt(a):
    parts = [f"{a['date']}  {a['age_months']:>5} mo"]
    if "weight" in a: parts.append(f"wt {a['weight']['kg']} kg p{a['weight']['pct']} (z{a['weight']['z']:+.2f})")
    lh = a.get("length") or a.get("height")
    if lh: parts.append(f"{'len' if 'length' in a else 'ht'} {lh['cm']} cm p{lh['pct']} (z{lh['z']:+.2f})")
    if "bmi" in a: parts.append(f"BMI {a['bmi']['value']} p{a['bmi']['pct']}")
    line = " | ".join(parts)
    if a.get("note"): line += f"  [{a['note']}]"
    for f in a["flags"]: line += f"\n    ! {f}"
    return line


def selftest():
    d = dt.date(2024, 1, 1)
    # WHO medians: boys weight 12 mo M=9.6479; boys length 12 mo M=75.7488; girls height 48 mo M=102.7312
    def at(mo): return d + dt.timedelta(days=round(mo * DAYS_PER_MONTH))
    a = assess("boy", d, at(12), 9.6479, 75.7488)
    assert abs(a["weight"]["z"]) < 0.02 and abs(a["length"]["z"]) < 0.02, a
    b = assess("girl", d, at(48), None, 102.7312)
    assert abs(b["height"]["z"]) < 0.02, b
    # standing measurement under 2 is lengthened by 0.7
    c = assess("boy", d, at(12), None, 75.0488, method="standing")
    assert abs(c["length"]["z"]) < 0.02, c
    # outlier detection: a height that drops 2.6 cm
    rows = [{"date": at(16.9), "kg": 10.2, "cm": 79.5}, {"date": at(18.6), "kg": 10.5, "cm": 87.0},
            {"date": at(20.4), "kg": 11.2, "cm": 84.4}]
    s = series("boy", d, rows)
    assert any("jumped" in f for f in s[1]["flags"]) and any("mismeasure" in f for f in s[2]["flags"]), s
    # WHO cut-off flag
    e = assess("boy", d, at(12), 7.0, 75.7)
    assert any("<3rd" in f for f in e["flags"]), e
    print("selftest ok")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("point", "series"):
        q = sub.add_parser(name)
        q.add_argument("--sex", choices=["boy", "girl"], required=True)
        q.add_argument("--dob", required=True)
        q.add_argument("--method", choices=["lying", "standing"])
        q.add_argument("--json", action="store_true")
        if name == "point":
            q.add_argument("--date", default=dt.date.today().isoformat())
            q.add_argument("--kg", type=float); q.add_argument("--cm", type=float)
        else:
            q.add_argument("--csv", required=True, help="date,kg,cm[,note]; '-' for stdin")
    sub.add_parser("selftest")
    a = p.parse_args()
    if a.cmd == "selftest":
        return selftest()
    dob = dt.date.fromisoformat(a.dob)
    if a.cmd == "point":
        r = [assess(a.sex, dob, dt.date.fromisoformat(a.date), a.kg, a.cm, a.method)]
    else:
        fh = sys.stdin if a.csv == "-" else open(a.csv)
        rows = []
        for rec in csv.reader(fh):
            if not rec or rec[0].strip().lower() in ("date", "") or rec[0].startswith("#"): continue
            f = lambda i: float(rec[i]) if len(rec) > i and rec[i].strip() else None
            rows.append({"date": dt.date.fromisoformat(rec[0].strip()), "kg": f(1), "cm": f(2),
                         "note": rec[3].strip() if len(rec) > 3 else ""})
        r = series(a.sex, dob, sorted(rows, key=lambda x: x["date"]), a.method)
    print(json.dumps(r, indent=1) if a.json else "\n".join(fmt(x) for x in r))


if __name__ == "__main__":
    main()
