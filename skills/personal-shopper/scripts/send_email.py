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


THUMB_PX = 240  # 3x the 72x96 render box's short side; sharp on retina, ~10-20 KB each
IMG_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _fetch_thumb(url: str) -> bytes | None:
    """Download one remote image and re-encode it as a small JPEG. None on any failure."""
    import io
    import urllib.request
    try:
        from PIL import Image
    except ImportError:
        return None
    if url.startswith("//"):
        url = "https:" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": IMG_UA, "Accept": "image/*"})
        raw = urllib.request.urlopen(req, timeout=25).read()
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
        im.thumbnail((THUMB_PX, int(THUMB_PX * 4 / 3)))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception as e:  # keep the remote URL rather than drop the picture
        print(f"  (image kept remote: {url[:70]}… — {str(e)[:60]})")
        return None


def inline_images(html: str) -> tuple[str, list[tuple[str, bytes]]]:
    """Embed every <img src="http..."> as a CID attachment (multipart/related).

    Remote-loaded images are unreliable in real inboxes: Apple Mail Privacy Protection proxies
    them (some retailer CDNs 403 the proxy), clients block remote content by default, and
    full-size product shots are 100-600 KB each. Embedding small thumbnails makes the email
    self-contained. Failures fall back to the original remote URL.
    """
    import re
    from concurrent.futures import ThreadPoolExecutor

    urls = list(dict.fromkeys(re.findall(r'<img[^>]+src="(https?:[^"]+|//[^"]+)"', html)))
    with ThreadPoolExecutor(8) as ex:
        thumbs = dict(zip(urls, ex.map(_fetch_thumb, urls)))
    images: list[tuple[str, bytes]] = []
    for n, u in enumerate(urls):
        data = thumbs.get(u)
        if not data:
            continue
        cid = f"img{n:02d}@shopper"
        html = html.replace(f'src="{u}"', f'src="cid:{cid}"')
        images.append((cid, data))
    print(f"  inlined {len(images)}/{len(urls)} images")
    return html, images


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--to", action="append", required=True, help="repeat for multiple recipients")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--html", required=True)
    ap.add_argument("--account", default="icloud")
    ap.add_argument("--config", type=pathlib.Path, help=f"accounts TOML (default {DEFAULT_CONFIG})")
    ap.add_argument("--from-addr", help="defaults to the account's own address")
    ap.add_argument("--dry-run", action="store_true", help="build and validate, do not send")
    ap.add_argument("--remote-images", action="store_true",
                    help="leave <img> URLs remote instead of embedding thumbnails (default: embed)")
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
    images: list[tuple[str, bytes]] = []
    if not args.remote_images:
        html, images = inline_images(html)
    msg.set_content(PLAIN_FALLBACK)
    msg.add_alternative(html, subtype="html")
    if images:
        html_part = msg.get_payload()[1]
        for cid, data in images:
            html_part.add_related(data, maintype="image", subtype="jpeg", cid=f"<{cid}>",
                                  filename=f"{cid.split('@')[0]}.jpg")

    if args.dry_run:
        print(f"DRY RUN — would send {args.subject!r} from {sender} to {', '.join(args.to)}")
        print(f"  {len(html):,} bytes of HTML, {len(images)} inline images "
              f"({sum(len(d) for _, d in images):,} bytes)")
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
