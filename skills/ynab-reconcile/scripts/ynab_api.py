#!/usr/bin/env python3
"""Small YNAB API helper for reconciliation work.

Why this exists: shells don't reliably word-split variables, and piping a token through
a shell var into curl inside a loop can yield empty requests. Use this module instead of
raw shell curl.

Credentials come from the environment, never from a file path baked into the script:
    YNAB_TOKEN   - Personal Access Token (YNAB > Account Settings > Developer Settings)
    YNAB_BUDGET  - Budget UUID, or "last-used" / "default"

Usage as a module:
    import sys; sys.path.insert(0, '<dir containing this file>')
    from ynab_api import call, txns
    accts = call('/accounts')['data']['accounts']
    for t in txns('<account_id>', '2026-06-01'): ...

Usage as CLI:
    export YNAB_TOKEN=... YNAB_BUDGET=...
    python3 ynab_api.py <account_id> <since_date>     # prints one line per txn
"""
import json
import os
import urllib.request

TOKEN = os.environ.get('YNAB_TOKEN')
BUDGET = os.environ.get('YNAB_BUDGET')
if not TOKEN or not BUDGET:
    raise SystemExit(
        'Set YNAB_TOKEN and YNAB_BUDGET in the environment before using this module. '
        'Token: YNAB > Account Settings > Developer Settings. Budget: the budget UUID, '
        'or "last-used" / "default".')
BASE = f'https://api.ynab.com/v1/budgets/{BUDGET}'


def call(path, method='GET', body=None):
    """Make a YNAB API call. path is relative to the budget, e.g. '/accounts'."""
    req = urllib.request.Request(
        BASE + path, method=method,
        headers={'Authorization': f'Bearer {TOKEN}',
                 'Content-Type': 'application/json'},
        data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def txns(account_id, since):
    """Non-deleted transactions for an account since YYYY-MM-DD."""
    data = call(f'/accounts/{account_id}/transactions?since_date={since}')
    return [t for t in data['data']['transactions'] if not t['deleted']]


def accounts():
    """All non-deleted, non-closed accounts, printed friendly."""
    return [a for a in call('/accounts')['data']['accounts']
            if not a['deleted'] and not a['closed']]


if __name__ == '__main__':
    import sys
    acct, since = sys.argv[1], sys.argv[2]
    for t in txns(acct, since):
        print(f"{t['date']} {t['amount']/1000:>10.2f} {t['cleared']:11s} "
              f"appr={str(t['approved'])[0]} "
              f"{str(t['payee_name'])[:42]:42s} "
              f"cat={str(t['category_name'])[:32]:32s} "
              f"import_id={t['import_id']} {t['id']}")
