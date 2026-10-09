#!/usr/bin/env python3
"""bill_watch_collect.py: pre-run collector for the bill-fetcher cron (read-only).

Scans the iCloud, Gmail and Proton inboxes for new "bill is ready" notices from KNOWN vendors
in the last N days, skips ones already handled (ledger ~/.hermes/bills/ledger.jsonl), and prints
one JSON line per pending notice. If nothing is pending it prints exactly NO_PENDING_BILLS.
"""
import json, re, subprocess, sys, datetime as dt
from pathlib import Path

LEDGER = Path("~/.hermes/bills/ledger.jsonl").expanduser()
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
# vendor -> (account, sender regex, subject regex, 1Password item or None, status)
VENDORS = {
    "Enercare":         ("icloud", r"billing\.enercare\.ca", r"bill is ready", "Enercare", "ready"),
    "Cogeco":           ("icloud", r"cogeco", r"bill is available", "Cogeco My Account (smankoo)", "ready"),
    "OVHcloud":         ("proton", r"ovhcloud", r"invoice (available|pending)", "OVH", "ready"),
    "AWS":              ("proton", r"invoicing@aws\.com", r"invoice available", None, "needs-1p-item"),
    "Enbridge Gas":     ("icloud", r"enbridgegas", r"ebill is ready", None, "needs-login"),
    "Burlington Hydro": ("icloud", r"burlingtonhydro", r"bill is ready", None, "needs-login"),
    "Rogers":           ("proton", r"rogers\.com", r"bill is ready", None, "needs-login"),
    "Fido":             ("proton", r"fidomobile", r"bill is ready", None, "needs-login"),
    "Cloudflare":       ("icloud", r"cloudflare", r"invoice is available", None, "needs-login"),
}

def done_keys():
    if not LEDGER.exists(): return set()
    return {json.loads(l).get("key") for l in LEDGER.read_text().splitlines() if l.strip()}

def envelopes(acct):
    r = subprocess.run(["himalaya", "--json", "envelope", "list", "-a", acct, "-s", "150"],
                       capture_output=True, text=True, timeout=120)
    try:
        d = json.loads(r.stdout)
    except Exception:
        print(json.dumps({"error": f"himalaya {acct} failed", "stderr": r.stderr[-200:]})); return []
    return d if isinstance(d, list) else (d.get("envelopes") or d.get("data") or [])

def main():
    seen = done_keys(); cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DAYS); out = []
    cache = {}
    for vendor, (acct, frm, subj, item, status) in VENDORS.items():
        cache.setdefault(acct, envelopes(acct))
        for e in cache[acct]:
            f = e.get("from"); f = f[0] if isinstance(f, list) and f else (f or {})
            addr = (f.get("email") or f.get("addr") or "") if isinstance(f, dict) else str(f)
            s = e.get("subject") or ""
            try:
                when = dt.datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00"))
            except Exception:
                continue
            if when.tzinfo is None: when = when.replace(tzinfo=dt.timezone.utc)
            if when < cut or not re.search(frm, addr, re.I) or not re.search(subj, s, re.I): continue
            key = f"{acct}:{e.get('message-id') or e.get('id')}"
            if key in seen: continue
            out.append({"vendor": vendor, "account": acct, "id": e.get("id"), "key": key, "date": when.isoformat(),
                        "subject": s, "op_item": item, "status": status})
    if not out: print("NO_PENDING_BILLS"); return
    for o in out: print(json.dumps(o))

if __name__ == "__main__":
    main()
