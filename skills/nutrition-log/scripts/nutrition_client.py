#!/usr/bin/env python3
"""nutrition_client.py — thin remote client for nutrition_server.py.

This is what the second agent ("shankar") runs on another machine. It forwards
its argv to the server's POST /run, prints the server's stdout and stderr, and
exits with the server's exit code — so `exit 3` (a possible duplicate) works
remotely exactly as it does locally.

Config: ~/.config/household-nutrition/client.json
  {"url": "http://100.93.163.69:3420", "token": "<bearer token>"}

Usage:
  nutrition_client.py day today --person tegh
  nutrition_client.py log paratha 1 --person tegh --packed --reported-by priyanka

Stdlib only; runs on Python 3.10+.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".config" / "household-nutrition" / "client.json"


def load_config():
    path = Path(os.environ.get("NUTRITION_CLIENT_CONFIG") or DEFAULT_CONFIG)
    if not path.exists():
        sys.stderr.write(f"error: missing client config at {path}\n")
        sys.exit(2)
    try:
        cfg = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"error: bad client config {path}: {e}\n")
        sys.exit(2)
    if not cfg.get("url") or not cfg.get("token"):
        sys.stderr.write(f"error: client config needs 'url' and 'token'\n")
        sys.exit(2)
    return cfg


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: nutrition_client.py <subcommand> [args...]\n")
        return 2
    cfg = load_config()
    url = cfg["url"].rstrip("/") + "/run"
    body = json.dumps({"argv": argv}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["token"]})
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except (ValueError, json.JSONDecodeError):
            payload = {"error": f"HTTP {e.code}"}
        sys.stderr.write(f"error: {payload.get('error', e)}\n")
        return 2
    except (urllib.error.URLError, TimeoutError) as e:
        sys.stderr.write(f"error: cannot reach nutrition server: {e}\n")
        return 2

    if payload.get("stdout"):
        sys.stdout.write(payload["stdout"])
        if not payload["stdout"].endswith("\n"):
            sys.stdout.write("\n")
    if payload.get("stderr"):
        sys.stderr.write(payload["stderr"])
        if not payload["stderr"].endswith("\n"):
            sys.stderr.write("\n")
    return int(payload.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
