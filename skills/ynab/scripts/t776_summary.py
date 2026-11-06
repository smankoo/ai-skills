#!/usr/bin/env python3
"""
t776_summary.py: total a rental property's YNAB transactions by CRA Form T776 line.

Answers "what does the accountant need for the rental this year?" from YNAB, without hand-adding.

How it works
- A JSON map says which YNAB category feeds which T776 line, e.g.
    {"categories": {"Mortgage": "8710*", "Home Insurance": "8690", "Property Tax (City X)": "9180"},
     "income_payees": "tenant name|House Rent", "rental_start": "2026-03-01", "owner_share": 0.5}
  A line ending in "*" means the category total is NOT the deductible amount (mortgage = principal +
  interest; only interest is deductible, line 8710, so take it from the lender's annual statement).
- Only transactions on/after rental_start count (CRA: expenses for the period the property was
  available for rent; before that the home was personal).
- Single transactions >= --capital-flag (default $1,500) are listed as "check: capital?" because
  equipment purchases/buyouts and improvements are capital (CCA, Chapter 4 of guide T4036), not
  line 8960 repairs.
- "payees": {"<regex>": "<line>"} catches rental costs booked in a mixed category (e.g. a handyman
  paid from a general household category). Category matches win over payee matches.
- income_payees is a regex over payee names for positive inflows (rent, line 8141 gross rents).
- owner_share prints each co-owner's share (co-owners each file their own T776, Part 2).

Usage
  YNAB_TOKEN=... YNAB_BUDGET_ID=... python3 t776_summary.py --map rental_map.json --year 2026
  ... --json             # machine-readable
  python3 t776_summary.py selftest   # offline test with fake transactions
"""
import argparse, json, os, re, sys
from collections import defaultdict

LINES = {"8141": "Gross rents", "8521": "Advertising", "8690": "Insurance", "8710": "Interest and bank charges",
         "8810": "Office expenses", "8860": "Professional fees", "8871": "Management and admin fees",
         "8960": "Repairs and maintenance", "9060": "Salaries, wages, benefits", "9180": "Property taxes",
         "9200": "Travel", "9220": "Utilities", "9281": "Motor vehicle", "9270": "Other expenses"}


def flatten(txs):
    for t in txs:
        if t.get("deleted"):
            continue
        subs = [s for s in (t.get("subtransactions") or []) if not s.get("deleted")]
        for s in (subs or [t]):
            yield {"date": t["date"], "amount": s["amount"] / 1000.0,
                   "category": s.get("category_name") or t.get("category_name"),
                   "payee": s.get("payee_name") or t.get("payee_name") or "", "memo": s.get("memo") or t.get("memo") or ""}


def summarise(txs, cfg, year, capital_flag=1500.0):
    start = max(cfg.get("rental_start", f"{year}-01-01"), f"{year}-01-01")
    end = f"{year}-12-31"
    cats = cfg.get("categories", {})
    inc_re = re.compile(cfg["income_payees"], re.I) if cfg.get("income_payees") else None
    pay_map = [(re.compile(k, re.I), v) for k, v in cfg.get("payees", {}).items()]
    lines = defaultdict(float); counts = defaultdict(int); flags = []; partial = set()
    for r in flatten(txs):
        if not (start <= r["date"] <= end):
            continue
        if r["amount"] > 0 and inc_re and inc_re.search(r["payee"]):
            lines["8141"] += r["amount"]; counts["8141"] += 1
            continue
        line = cats.get(r["category"]) or next((v for k, v in pay_map if k.search(r["payee"])), None)
        if not line or r["amount"] >= 0:
            continue
        if line.endswith("*"):
            partial.add(line.rstrip("*"))
        line = line.rstrip("*")
        lines[line] += -r["amount"]; counts[line] += 1
        if -r["amount"] >= capital_flag and line not in partial:
            flags.append(r)
    share = float(cfg.get("owner_share", 1.0))
    out = {"year": year, "period": [start, end], "owner_share": share, "lines": {}, "capital_check": flags,
           "needs_statement": sorted(partial)}
    for k in sorted(lines):
        out["lines"][k] = {"name": LINES.get(k, "?"), "total": round(lines[k], 2), "count": counts[k],
                           "your_share": round(lines[k] * share, 2), "partial": k in partial}
    return out


def render(o):
    print(f"T776 summary {o['year']} (period {o['period'][0]} to {o['period'][1]}, owner share {o['owner_share']:.0%})")
    for k, v in o["lines"].items():
        note = "  <- NOT deductible as is: use the interest figure from the lender's annual statement" if v["partial"] else ""
        print(f"  {k} {v['name']:<28} ${v['total']:>11,.2f}  ({v['count']} tx)  your share ${v['your_share']:,.2f}{note}")
    if o["capital_check"]:
        print("Check with the accountant (capital or current?):")
        for r in o["capital_check"]:
            print(f"  {r['date']}  ${-r['amount']:,.2f}  {r['payee']}  [{r['category']}] {r['memo'][:60]}")


def selftest():
    txs = [
        {"date": "2026-02-01", "amount": -5000000, "category_name": "Mortgage", "payee_name": "Bank"},  # before start
        {"date": "2026-03-02", "amount": -5421920, "category_name": "Mortgage", "payee_name": "Bank"},
        {"date": "2026-04-01", "amount": 2800000, "category_name": "Inflow", "payee_name": "Tenant A"},
        {"date": "2026-04-05", "amount": -250000, "category_name": "Repairs", "payee_name": "Plumber"},
        {"date": "2026-08-26", "amount": -10920390, "category_name": "Repairs", "payee_name": "Equipment Co"},
        {"date": "2026-05-01", "amount": -1000, "category_name": None, "payee_name": "Split", "subtransactions": [
            {"amount": -100000, "category_name": "Insurance", "payee_name": "Insurer"},
            {"amount": -50000, "category_name": "Groceries", "payee_name": "Store"}]},
        {"date": "2026-09-22", "amount": -150000, "category_name": "Household", "payee_name": "Handyman H"},
        {"date": "2027-01-02", "amount": -999000, "category_name": "Insurance", "payee_name": "Insurer"},  # next year
    ]
    cfg = {"categories": {"Mortgage": "8710*", "Repairs": "8960", "Insurance": "8690"},
           "payees": {"handyman": "8960"}, "income_payees": "tenant", "rental_start": "2026-03-01", "owner_share": 0.5}
    o = summarise(txs, cfg, 2026)
    L = o["lines"]
    assert L["8710"]["total"] == 5421.92 and L["8710"]["partial"], L["8710"]
    assert L["8141"]["total"] == 2800.0
    assert L["8960"]["total"] == 11320.39 and L["8960"]["count"] == 3, L["8960"]
    assert L["8690"]["total"] == 100.0, L["8690"]
    assert len(o["capital_check"]) == 1 and o["capital_check"][0]["payee"] == "Equipment Co"
    assert o["needs_statement"] == ["8710"]
    render(o)
    print("selftest ok")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, help="JSON map file (see docstring)")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--capital-flag", type=float, default=1500.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(os.path.expanduser(a.map)))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ynab_client import YNABClient
    tok, bud = os.environ.get("YNAB_TOKEN"), os.environ.get("YNAB_BUDGET_ID", "last-used")
    if not tok:
        sys.exit("YNAB_TOKEN not set")
    txs = YNABClient(tok, bud).get_transactions(since_date=f"{a.year}-01-01")
    o = summarise(txs, cfg, a.year, a.capital_flag)
    print(json.dumps(o, indent=1, default=str)) if a.json else render(o)


if __name__ == "__main__":
    main()
