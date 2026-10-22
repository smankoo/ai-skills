#!/usr/bin/env python3
"""Forward selected pages of a fetched bill to a standing recipient.

Rules come from ~/.config/bill-fetcher/forwards.json (kept out of the repo because it holds PII):
  {"Fido": {"to": "...", "pages": [1], "forbid": ["NAME1", "NAME2"], "account": "icloud"}}

Steps: extract the pages, refuse to send if any forbidden string appears in them, email the result
from the configured himalaya account, save a copy to Sent, and log to ~/.hermes/bills/forwards.jsonl.
It is idempotent: a vendor/bill-date already in the log is skipped unless --force is given.

Usage: bill_forward_summary.py --vendor Fido --pdf bill.pdf --bill-date 2026-11-16 --amount 138.43 [--dry-run] [--force]
"""
import argparse, json, os, subprocess, sys, tempfile, datetime
from email.message import EmailMessage

CFG = os.path.expanduser("~/.config/bill-fetcher/forwards.json")
LOG = os.path.expanduser("~/.hermes/bills/forwards.jsonl")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--bill-date", required=True)
    ap.add_argument("--amount", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    rules = json.load(open(CFG))
    rule = rules.get(a.vendor)
    if not rule:
        print(f"no forward rule for {a.vendor}; nothing to do")
        return 0
    key = f"{a.vendor}:{a.bill_date}:{rule['to']}"
    if os.path.exists(LOG) and not a.force:
        for line in open(LOG):
            if json.loads(line).get("key") == key:
                print(f"already forwarded {key}; skip")
                return 0

    tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    parts = []
    for p in rule.get("pages", [1]):
        out = os.path.join(tmp, f"p{p}.pdf")
        r = run(["pdfseparate", "-f", str(p), "-l", str(p), a.pdf, out])
        if r.returncode:
            sys.exit(f"pdfseparate failed on page {p}: {r.stderr}")
        parts.append(out)
    fname = f"{a.vendor}_{a.bill_date}_summary.pdf"
    outpdf = os.path.join(tmp, fname)
    if len(parts) == 1:
        os.replace(parts[0], outpdf)
    else:
        r = run(["pdfunite", *parts, outpdf])
        if r.returncode:
            sys.exit(f"pdfunite failed: {r.stderr}")

    text = run(["pdftotext", outpdf, "-"]).stdout.upper()
    if not text.strip():
        sys.exit("REFUSED: extracted pages have no text layer, so the name check can't run")
    hits = [f for f in rule.get("forbid", []) if f.upper() in text]
    if hits:
        sys.exit(f"REFUSED: extracted pages still contain forbidden strings: {hits}")

    m = EmailMessage()
    m["From"] = rule["from"]
    m["To"] = rule["to"]
    m["Subject"] = f"{a.vendor} bill {a.bill_date}: ${a.amount} (summary page)"
    m.set_content(f"{a.vendor} bill dated {a.bill_date}, total ${a.amount}. Summary page only.\n")
    m.add_attachment(open(outpdf, "rb").read(), maintype="application", subtype="pdf", filename=fname)
    raw = bytes(m)
    if a.dry_run:
        print(f"DRY RUN ok: would send {fname} ({len(raw)} bytes) to {rule['to']}; name check passed")
        return 0
    acct = rule.get("account", "icloud")
    r = run(["himalaya", "message", "send", "-a", acct], input=raw.decode("utf-8", "surrogateescape"))
    if r.returncode or "success" not in (r.stdout + r.stderr).lower():
        sys.exit(f"send failed: {r.stdout} {r.stderr}")
    run(["himalaya", "message", "save", "-a", acct, "-m", rule.get("sent_folder", "Sent Messages")],
        input=raw.decode("utf-8", "surrogateescape"))
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({"key": key, "vendor": a.vendor, "bill_date": a.bill_date, "amount": a.amount,
                            "to": rule["to"], "file": fname,
                            "at": datetime.datetime.now().astimezone().isoformat()}) + "\n")
    print(f"SENT {fname} to {rule['to']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
