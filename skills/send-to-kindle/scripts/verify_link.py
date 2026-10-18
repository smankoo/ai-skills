#!/usr/bin/env python3
"""Open an Amazon Send-to-Kindle verification link ONCE and record the result.

The links are single-use. Two failure modes this script prevents:
  1. Burning the link without reading the reply: Amazon gzips the page, so a plain
     fetch prints binary noise and you never learn whether it said "verified".
  2. Two openers racing (a chat session and a mail-processing job both open it):
     the second one gets "That link isn't working" and wrongly reports a failure.

Every opener should call this script instead of curl. It keeps a shared ledger
(JSONL) keyed by the request UUID. If the link was already opened, it prints the
earlier result and does NOT fetch again.

Usage:
  verify_link.py <verify-url> [--title "Book title"] [--by "who is opening it"]
  verify_link.py --status <verify-url-or-uuid>

Output (one line JSON): {"result": "verified"|"already_used"|"error"|"unknown", ...}
Exit code: 0 verified / already_used-after-our-own-verify, 1 otherwise.
Ledger: $KINDLE_VERIFY_LEDGER or ~/.local/state/send-to-kindle/verify.jsonl
"""
import argparse, gzip, json, os, re, sys, time, urllib.request, zlib

LEDGER = os.path.expanduser(os.environ.get(
    "KINDLE_VERIFY_LEDGER", "~/.local/state/send-to-kindle/verify.jsonl"))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def req_id(s):
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", s)
    return m.group(1) if m else s.strip()


def load():
    out = {}
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                r = json.loads(line)
                out.setdefault(r["id"], []).append(r)
            except Exception:
                pass
    return out


def classify(text):
    t = text.lower()
    if "successfully verified" in t or "verified!" in t:
        return "verified"
    if "isn't working" in t or "isn&#39;t working" in t or "is not working" in t or "expired" in t:
        return "already_used"
    if "something went wrong" in t:
        return "error"
    return "unknown"


def fetch(url):
    r = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-CA,en;q=0.9"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw, enc, code = resp.read(), resp.headers.get("Content-Encoding", ""), resp.status
    if enc == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw)
    return code, raw.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--title", default="")
    ap.add_argument("--by", default=os.environ.get("USER", "?"))
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    rid = req_id(a.url)
    # Only a fetch that actually reached the page "uses" the link; network/5xx errors may retry.
    prior = [r for r in load().get(rid, []) if r.get("http")]
    if a.status or prior:
        last = prior[-1] if prior else {"id": rid, "result": "not_opened"}
        print(json.dumps(dict(last, note="from ledger; link NOT re-opened")))
        return 0 if last.get("result") == "verified" else 1
    if not a.url.startswith("https://www.amazon."):
        print(json.dumps({"id": rid, "result": "error", "note": "not an amazon verify URL"}))
        return 1
    try:
        code, html = fetch(a.url)
        res = classify(html)
        snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        m = re.search(r"(verified[^.]{0,80}|isn.t working[^.]{0,80}|went wrong[^.]{0,80})",
                      snippet, re.I)
        rec = {"id": rid, "result": res, "http": code, "said": m.group(0) if m else "",
               "title": a.title, "by": a.by, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    except Exception as e:
        rec = {"id": rid, "result": "error", "note": str(e)[:200], "title": a.title,
               "by": a.by, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))
    return 0 if rec["result"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
