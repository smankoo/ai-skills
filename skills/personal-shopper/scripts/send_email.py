#!/usr/bin/env python3
"""Send one HTML email via SMTP, reading credentials at runtime.

Credentials come from a TOML file — never hardcoded, never printed. Default path is
~/.config/owlpost/accounts.toml; override with --config or $SHOPPER_ACCOUNTS_FILE.
Expected shape:

    [accounts.icloud]
    email = "<your-address>"
    password = "<app-specific-password>"   # never committed; this file lives outside the repo
    smtp_host = "smtp.mail.me.com"
    imap_host = "imap.mail.me.com"         # optional; enables the Sent-folder append

Also APPENDs the message to the Sent folder, because some providers' SMTP does not.

Usage:
    python3 send_email.py --to a@b.com [--to c@d.com] --subject "..." --html out/email.html
    python3 send_email.py ... --account icloud --config ~/my/accounts.toml --dry-run
"""
from __future__ import annotations

import argparse
import imaplib
import os
import pathlib
import smtplib
import ssl
import sys
import time
import tomllib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

DEFAULT_CONFIG = pathlib.Path.home() / ".config" / "owlpost" / "accounts.toml"
PLAIN_FALLBACK = "This message is formatted in HTML. Please view it in an HTML-capable mail client."


def default_config() -> pathlib.Path:
    return pathlib.Path(os.environ.get("SHOPPER_ACCOUNTS_FILE") or DEFAULT_CONFIG).expanduser()


def load_account(name: str, config: pathlib.Path) -> dict:
    if not config.exists():
        sys.exit(f"No credentials file at {config} (set --config or $SHOPPER_ACCOUNTS_FILE)")
    cfg = tomllib.loads(config.read_text())
    try:
        return cfg["accounts"][name]
    except KeyError:
        available = ", ".join(cfg.get("accounts", {})) or "none"
        sys.exit(f"No account {name!r} in {config}. Available: {available}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--to", action="append", required=True, help="repeat for multiple recipients")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--html", required=True)
    ap.add_argument("--account", default="icloud")
    ap.add_argument("--config", type=pathlib.Path, help=f"accounts TOML (default {DEFAULT_CONFIG})")
    ap.add_argument("--from-addr", help="defaults to the account's own address")
    ap.add_argument("--dry-run", action="store_true", help="build and validate, do not send")
    args = ap.parse_args()

    html = pathlib.Path(args.html).read_text()
    if "{{" in html:
        sys.exit(f"{args.html} still contains an unfilled {{{{placeholder}}}} — refusing to send")

    acct = load_account(args.account, args.config.expanduser() if args.config else default_config())
    sender = args.from_addr or acct["email"]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(args.to)
    msg["Subject"] = args.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(PLAIN_FALLBACK)
    msg.add_alternative(html, subtype="html")

    if args.dry_run:
        print(f"DRY RUN — would send {args.subject!r} from {sender} to {', '.join(args.to)}")
        print(f"  {len(html):,} bytes of HTML")
        return 0

    ctx = ssl.create_default_context()
    with smtplib.SMTP(acct["smtp_host"], acct.get("smtp_port", 587), timeout=60) as s:
        s.starttls(context=ctx)
        s.login(acct["email"], acct["password"])
        s.send_message(msg)
    print(f"SENT: {args.subject}")

    # Many providers (iCloud among them) do not auto-file SMTP sends. Append manually.
    if not acct.get("imap_host"):
        return 0
    try:
        with imaplib.IMAP4_SSL(acct["imap_host"], acct.get("imap_port", 993)) as im:
            im.login(acct["email"], acct["password"])
            raw = msg.as_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            for folder in ('"Sent Messages"', "Sent", '"[Gmail]/Sent Mail"'):
                try:
                    if im.append(folder, "\\Seen", imaplib.Time2Internaldate(time.time()), raw)[0] == "OK":
                        print(f"  saved to {folder}")
                        break
                except Exception:
                    continue
    except Exception as e:
        print(f"  (Sent-folder append skipped: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
