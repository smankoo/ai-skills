#!/usr/bin/env python3
"""
account_forecast.py: forecast an account's balance N days ahead and flag the low point.

Answers "how much do I need to top up account X, and by when?" without guessing.

How it works
1. Start from the account's CLEARED balance (uncleared transfers that never land are a known
   trap; pass --use-working to start from YNAB's working balance instead).
2. Detect recurring OUTFLOWS from the account's own history (default 180 days):
   transactions are grouped by exact amount, since payee names drift ("Hyundai Motor Finance"
   becomes "Hyundai" after a bank feed change, but the amount stays the same). A group counts
   as recurring when it has >=3 hits, a steady cadence (biweekly 12-16 d or monthly 26-35 d),
   and its last hit is recent (within 1.6 cadences), so stopped payments drop out.
   A same-amount re-debit soon after the original (an NSF bounce then a retry: the Sep 2 2026
   mortgage was re-drafted Sep 14) is collapsed (<8 d for biweekly, <18 d for monthly).
3. Add YNAB scheduled transactions for the account (if any) on top.
4. Optionally (--include-income) project recurring INFLOWS the same way. This is off by default
   because irregular transfers in are the thing being planned.

Usage
  YNAB_TOKEN=... YNAB_BUDGET_ID=... python3 account_forecast.py "BMO Chequing" --days 60
  ... --buffer 1000         # warn when the projected balance dips below this
  ... --json                # machine-readable output

The account argument is a case-insensitive substring of the YNAB account name.
Dates are nominal: banks shift debits that fall on a weekend or holiday to the next business
day, so treat each date as +/-2 days.
"""
import argparse, json, os, sys, statistics
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ynab_client import YNABClient  # noqa: E402


def add_months(d, n, dom):
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    for day in (dom, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue


def detect(txns, sign, today):
    groups = defaultdict(list)
    for t in txns:
        a = t["amount"]
        if (a < 0) != (sign < 0) or a == 0:
            continue
        groups[a].append(t)
    out = []
    for amt, ts in groups.items():
        ts.sort(key=lambda t: t["date"])
        raw = [date.fromisoformat(t["date"]) for t in ts if date.fromisoformat(t["date"]) <= today]

        def collapse(win):  # bounce + re-debit of the same amount counts once
            ds = []
            for d in raw:
                if ds and (d - ds[-1]).days < win:
                    continue
                ds.append(d)
            return ds

        kind = None
        for k, period, win, lo, hi, glo, ghi in (("biweekly", 14, 8, 12, 16, 10, 18),
                                                ("monthly", 30, 18, 26, 35, 24, 38)):
            dates = collapse(win)
            if len(dates) < 3:
                continue
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            if lo <= statistics.median(gaps) <= hi and all(glo <= x <= ghi for x in gaps[-3:]):
                kind = k
                break
        if not kind:
            continue
        last = dates[-1]
        if (today - last).days > period * 1.6:
            continue  # stopped
        payee = (ts[-1].get("payee_name") or "?")
        dom = statistics.mode([d.day for d in dates]) if kind == "monthly" else None
        out.append(dict(amount=amt / 1000, payee=payee, kind=kind, last=last, dom=dom, hits=len(dates)))
    return out


def project(rule, today, end):
    occ = []
    if rule["kind"] == "biweekly":
        d = rule["last"] + timedelta(days=14)
        while d <= today:
            d += timedelta(days=14)
        while d <= end:
            occ.append(d); d += timedelta(days=14)
    else:
        n = 1
        while True:
            d = add_months(rule["last"], n, rule["dom"]); n += 1
            if d <= today:
                continue
            if d > end:
                break
            occ.append(d)
    return occ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("account")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--lookback", type=int, default=180)
    ap.add_argument("--buffer", type=float, default=1000.0)
    ap.add_argument("--include-income", action="store_true")
    ap.add_argument("--use-working", action="store_true")
    ap.add_argument("--today", help="YYYY-MM-DD (testing)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tok, bud = os.environ.get("YNAB_TOKEN"), os.environ.get("YNAB_BUDGET_ID", "last-used")
    if not tok:
        sys.exit("YNAB_TOKEN not set")
    c = YNABClient(tok, bud)
    today = date.fromisoformat(a.today) if a.today else date.today()
    end = today + timedelta(days=a.days)
    accts = [x for x in c.get_accounts() if a.account.lower() in x["name"].lower()]
    if len(accts) != 1:
        sys.exit(f"account match must be unique; got {[x['name'] for x in accts]}")
    acct = accts[0]
    start = (acct["balance"] if a.use_working else acct["cleared_balance"]) / 1000
    since = (today - timedelta(days=a.lookback)).isoformat()
    txns = c.get(f"{c.bp}/accounts/{acct['id']}/transactions", {"since_date": since})["data"]["transactions"]
    txns = [t for t in txns if not t["deleted"]]
    rules = detect(txns, -1, today) + (detect(txns, 1, today) if a.include_income else [])
    events = []
    for r in rules:
        for d in project(r, today, end):
            events.append((d, r["amount"], f"{r['payee']} ({r['kind']})"))
    try:
        sched = c.get(f"{c.bp}/scheduled_transactions")["data"]["scheduled_transactions"]
    except Exception:
        sched = []
    known = {round(r["amount"], 2) for r in rules}
    for s in sched:
        if s["deleted"] or s["account_id"] != acct["id"]:
            continue
        d, amt = date.fromisoformat(s["date_next"]), s["amount"] / 1000
        if today < d <= end and round(amt, 2) not in known:
            events.append((d, amt, f"{s.get('payee_name') or '?'} (scheduled)"))
    events.sort()
    bal, low, low_d, rows = start, start, today, []
    for d, amt, label in events:
        bal += amt
        rows.append(dict(date=d.isoformat(), amount=round(amt, 2), label=label, balance=round(bal, 2)))
        if bal < low:
            low, low_d = bal, d
    first_below = next((r for r in rows if r["balance"] < a.buffer), None)
    need = max(0.0, a.buffer - low)
    res = dict(account=acct["name"], start_balance=round(start, 2),
               start_basis="working" if a.use_working else "cleared",
               uncleared=round((acct["balance"] - acct["cleared_balance"]) / 1000, 2),
               window=f"{today}..{end}", rules=[{**r, "last": r["last"].isoformat()} for r in rules],
               events=rows, low_point=round(low, 2), low_date=low_d.isoformat(),
               first_below_buffer=first_below, topup_needed=round(need, 2), buffer=a.buffer)
    if a.json:
        print(json.dumps(res, indent=2)); return
    print(f"{acct['name']}: start {start:,.2f} ({res['start_basis']}; uncleared {res['uncleared']:,.2f})")
    print("Recurring detected:")
    for r in rules:
        print(f"  {r['amount']:>10,.2f}  {r['kind']:<8} {r['payee']}  (last {r['last']}, {r['hits']} hits)")
    print(f"Projection {today} -> {end}:")
    for r in rows:
        flag = "  <-- below buffer" if r["balance"] < a.buffer else ""
        print(f"  {r['date']}  {r['amount']:>10,.2f}  bal {r['balance']:>10,.2f}  {r['label']}{flag}")
    print(f"Low point {low:,.2f} on {low_d}. ", end="")
    if need:
        by = first_below["date"] if first_below else low_d
        print(f"Top up {need:,.2f} before {by} to keep {a.buffer:,.0f} buffer.")
    else:
        print(f"Stays above the {a.buffer:,.0f} buffer.")


if __name__ == "__main__":
    main()
