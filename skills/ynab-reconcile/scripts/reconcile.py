#!/usr/bin/env python3
"""Reconcile one YNAB account against a downloaded bank file.

Parses an OFX or a generic CSV, fetches YNAB transactions, and reports the exact
discrepancy sets using a robust multiset-by-amount match (dates are unreliable across
bank posting lag, so we match on amount and only use dates to disambiguate).

    export YNAB_TOKEN=... YNAB_BUDGET=...
    python3 reconcile.py <account_id> <bank_file> [--since YYYY-MM-DD]
                         [--start YYYYMMDD] [--end YYYYMMDD]

--start/--end restrict the *bank statement window*. Critical for OFX credit-card
exports that begin later than the account's YNAB history: YNAB items dated before the
window are part of the bank's OPENING balance, NOT phantoms. Pass the window to avoid
flagging them. If omitted, the min/max bank txn dates are used.

Output: three lists (bank-not-in-YNAB -> add; YNAB-not-on-bank -> classify then
delete/keep; and the balance target). NOTHING is written -- this is analysis only.
Read the "Analysis gotchas" section of SKILL.md before acting on the output.

CSV column names vary by bank/broker. This script tries a few common ones
(amount/net_cash_amount, merchant/name/transaction_type, transaction_date/date,
status) and falls back gracefully; pass your export through a quick header check
first if it uses different names, and adjust the parse_csv() lookups.
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, '/'.join(__file__.split('/')[:-1]))
from ynab_api import txns  # noqa: E402


def parse_ofx(path):
    txt = open(path, encoding='cp1252').read()
    out = []
    for m in re.finditer(r'<STMTTRN>(.*?)</STMTTRN>', txt, re.S):
        b = m.group(1)

        def f(tag, b=b):
            mm = re.search(rf'<{tag}>([^<\r\n]*)', b)
            return mm.group(1).strip() if mm else ''
        out.append({'date': f('DTPOSTED')[:8], 'amt': round(float(f('TRNAMT')), 2),
                    'name': f('NAME'), 'status': 'posted'})
    bal = re.search(r'<LEDGERBAL>.*?<BALAMT>([^<\r\n]*)', txt, re.S)
    ledger = round(float(bal.group(1)), 2) if bal else None
    return out, ledger


def parse_csv(path):
    out = []
    for r in csv.DictReader(open(path)):
        # Column names vary by institution; try the common ones and fall back gracefully.
        amt = round(float(r.get('amount') or r.get('net_cash_amount')), 2)
        name = (r.get('merchant') or r.get('name') or r.get('transaction_type')
                or '').strip()
        d = (r.get('transaction_date') or r.get('date') or '').replace('-', '')[:8]
        out.append({'date': d, 'amt': amt, 'name': name,
                    'status': (r.get('status') or 'posted').lower()})
    return out, None


def d8(s):
    s = s.replace('-', '')
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('account_id')
    ap.add_argument('bank_file')
    ap.add_argument('--since', default='2020-01-01')
    ap.add_argument('--start')
    ap.add_argument('--end')
    ap.add_argument('--tol', type=int, default=8, help='date tolerance in days')
    a = ap.parse_args()

    bank, ledger = (parse_ofx if a.bank_file.lower().endswith('.ofx')
                    else parse_csv)(a.bank_file)
    start = a.start or min(o['date'] for o in bank)
    end = a.end or max(o['date'] for o in bank)
    win = [o for o in bank if start <= o['date'] <= end]
    posted = [o for o in win if o['status'] in ('posted', 'completed')]
    pending = [o for o in win if o['status'] == 'pending']

    y = txns(a.account_id, a.since)
    # Match candidates include YNAB items dated within the window PLUS items dated up
    # to `tol` days before it -- bank posting lag means a YNAB txn dated 06-11 can post
    # 06-12 (just inside the window). Without this, those boundary items show as false
    # "add" suggestions. Leftover pre-window items are the opening balance, not phantoms.
    lo = _shift(start, -a.tol)
    cand = [t for t in y if lo <= t['date'].replace('-', '') <= end]

    ybyamt = defaultdict(list)
    for t in cand:
        ybyamt[round(t['amount'] / 1000, 2)].append(t)

    bank_unmatched = []
    for o in posted:
        lst = ybyamt.get(o['amt'])
        # disambiguate by nearest date if multiple same-amount candidates
        if lst:
            lst.sort(key=lambda t: abs((d8(t['date']) - d8(o['date'])).days))
            lst.pop(0)
        else:
            bank_unmatched.append(o)
    # Only items dated within the window are phantom candidates; leftover pre-window
    # matches were opening-balance items that happened not to pair with a bank row.
    leftover = [t for lst in ybyamt.values() for t in lst]
    y_unmatched = [t for t in leftover if t['date'].replace('-', '') >= start]
    prewin = [t for t in y if lo <= t['date'].replace('-', '') < start]

    print(f"=== Account {a.account_id}  window {start}..{end}")
    if ledger is not None:
        print(f"Bank ledger balance: {ledger:.2f}")
    print(f"Bank posted txns in window: {len(posted)}  "
          f"pending: {len(pending)}  net posted: "
          f"{round(sum(o['amt'] for o in posted), 2)}")
    print(f"Implied bank OPENING balance (before window): "
          f"{round(ledger - sum(o['amt'] for o in posted), 2) if ledger else '?'}")

    print("\n-- BANK not in YNAB  -> ADD (real, categorize per your own conventions):")
    for o in sorted(bank_unmatched, key=lambda x: x['date']):
        print(f"   {o['date']} {o['amt']:>9.2f}  {o['name']}")

    print("\n-- YNAB (in window) not on bank  -> CLASSIFY (phantom/pending/wrong-acct):")
    for t in sorted(y_unmatched, key=lambda x: x['date']):
        origin = 'manual' if not t['import_id'] else 'imported'
        print(f"   {t['date']} {t['amount']/1000:>9.2f} {t['cleared']:10s} "
              f"[{origin}] {t['payee_name']}  {t['id']}")

    if pending:
        print("\n-- Bank PENDING (not in ledger balance; may already be in YNAB):")
        for o in pending:
            print(f"   {o['date']} {o['amt']:>9.2f}  {o['name']}")

    if prewin:
        print(f"\n-- NOTE: {len(prewin)} YNAB items dated before the window are part "
              f"of the bank OPENING balance -- NOT phantoms. (Not listed.)")


def _shift(yyyymmdd, days):
    from datetime import timedelta
    dt = d8(yyyymmdd) + timedelta(days=days)
    return dt.strftime('%Y%m%d')


if __name__ == '__main__':
    main()
