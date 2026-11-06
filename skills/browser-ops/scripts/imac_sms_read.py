#!/usr/bin/env python3
"""Read recent SMS/iMessage texts from the iMac's Messages DB (chat.db).

Usage: imac_sms_read.py [--minutes N] [--grep REGEX] [--code]
  --code  print only the newest 4-8 digit code from matching messages.
Newer macOS keeps the text in `attributedBody` (typedstream) with `text`
NULL, so this decodes the NSString payload from the blob.
Runs ON the iMac (needs Full Disk Access for the ssh/terminal process).
"""
import argparse, re, sqlite3, os, time

def decode(blob):
    if not blob:
        return ''
    try:
        b = blob.split(b'NSString', 1)[1][5:]
        n = b[0]
        if n == 0x81:
            n = int.from_bytes(b[1:3], 'little'); s = b[3:3 + n]
        elif n == 0x82:
            n = int.from_bytes(b[1:4], 'little'); s = b[4:4 + n]
        else:
            s = b[1:1 + n]
        return s.decode('utf-8', 'ignore')
    except Exception:
        return ''

ap = argparse.ArgumentParser()
ap.add_argument('--minutes', type=int, default=30)
ap.add_argument('--grep', default='')
ap.add_argument('--code', action='store_true')
a = ap.parse_args()
con = sqlite3.connect('file:' + os.path.expanduser('~/Library/Messages/chat.db') + '?mode=ro', uri=True)
since = (time.time() - a.minutes * 60 - 978307200) * 1e9
rows = con.execute("""SELECT m.date, h.id, m.text, m.attributedBody FROM message m
  LEFT JOIN handle h ON h.ROWID=m.handle_id WHERE m.is_from_me=0 AND m.date > ?
  ORDER BY m.date DESC""", (since,)).fetchall()
for d, sender, text, ab in rows:
    body = text or decode(ab)
    if a.grep and not re.search(a.grep, body or '', re.I):
        continue
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d / 1e9 + 978307200))
    if a.code:
        m = re.search(r'(?<!\d)(\d{4,8})(?!\d)', body or '')
        if m:
            print(m.group(1)); break
        continue
    print(f'{ts} | {sender} | {body}')
