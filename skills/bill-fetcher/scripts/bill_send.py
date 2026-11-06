#!/usr/bin/env python3
"""bill_send.py: email a fetched bill PDF back to Sumeet, threaded as a reply to the original notice.

Usage:
  bill_send.py --account icloud --orig-id 9016 --pdf /path/bill.pdf --vendor Enercare \
               --amount 79.21 --due 2026-10-28 --bill-date 2026-10-08 [--to sumeet@...] [--dry-run]

Reads the original message's Message-ID and Subject via himalaya, so the reply threads correctly.
Sends from the iCloud account (SMTP creds come from ~/.config/owlpost/accounts.toml at runtime and are
never printed). The PDF goes as a normal attachment (Content-Disposition: attachment).
"""
import argparse, email.utils, re, smtplib, ssl, subprocess, sys, tomllib
from email.message import EmailMessage
from pathlib import Path

def orig_headers(account, mid):
    raw = subprocess.run(["himalaya", "message", "read", "-a", account, "--raw", str(mid)],
                         capture_output=True, timeout=90).stdout
    import email as _e
    msg = _e.message_from_bytes(raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n" if b"\r\n\r\n" in raw else raw)
    from email.header import decode_header, make_header
    subj = str(make_header(decode_header(msg.get("Subject", "Your bill"))))
    return msg.get("Message-ID"), subj

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True); ap.add_argument("--orig-id", required=True)
    ap.add_argument("--pdf", required=True); ap.add_argument("--vendor", required=True)
    ap.add_argument("--amount"); ap.add_argument("--due"); ap.add_argument("--bill-date")
    ap.add_argument("--saved-to", default="iCloud Drive › Bills")
    ap.add_argument("--to", default=None); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    pdf = Path(a.pdf); data = pdf.read_bytes()
    if data[:4] != b"%PDF": sys.exit("refusing: not a PDF")
    cfg = tomllib.loads(Path("~/.config/owlpost/accounts.toml").expanduser().read_text())["accounts"]["icloud"]
    to = a.to or cfg["email"]
    msgid, subj = orig_headers(a.account, a.orig_id)
    m = EmailMessage()
    m["From"] = cfg["email"]; m["To"] = to
    m["Subject"] = ("Re: " + subj) if not subj.lower().startswith("re:") else subj
    m["Date"] = email.utils.formatdate(localtime=True); m["Message-ID"] = email.utils.make_msgid(domain="mankoo.ca")
    if msgid: m["In-Reply-To"] = msgid; m["References"] = msgid
    lines = [f"{a.vendor} bill attached."]
    if a.amount: lines.append(f"Amount: ${a.amount}")
    if a.due: lines.append(f"Due: {a.due}")
    if a.bill_date: lines.append(f"Bill date: {a.bill_date}")
    lines.append(f"Saved to: {a.saved_to}")
    m.set_content("\n".join(lines) + "\n")
    m.add_attachment(data, maintype="application", subtype="pdf", filename=pdf.name)
    if a.dry_run:
        print("DRY RUN ok:", m["Subject"], "| in-reply-to:", bool(msgid), "| bytes:", len(data)); return
    with smtplib.SMTP(cfg.get("smtp_host", "smtp.mail.me.com"), int(cfg.get("smtp_port", 587)), timeout=60) as s:
        s.starttls(context=ssl.create_default_context()); s.login(cfg["email"], cfg["password"]); s.send_message(m)
    print("sent:", m["Subject"], "| threaded:", bool(msgid))

if __name__ == "__main__":
    main()
