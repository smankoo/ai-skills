#!/usr/bin/env python3
"""nutrition_server.py — stdlib HTTP front door to nutrition.py for a 2nd agent.

A second agent ("shankar", on another tailnet machine) talks to this server via
nutrition_client.py. The server runs nutrition.py as a subprocess (no shell),
enforcing who may do what:

  POST /run  {"argv": ["day", "today", "--person", "tegh"]}
      Authorization: Bearer <token>
      -> {"exit": <code>, "stdout": "...", "stderr": "..."}

  GET /health -> {"ok": true, "schema": "2"}   (no auth)

Rules enforced here (not trusted to the client):
  - the token maps to an agent name; the server sets NUTRITION_AGENT=<agent> for
    the child and strips any client-supplied --logged-by (clients cannot forge it);
  - log/log-custom/edit/rm/eaten/body/water REQUIRE an explicit --person (400);
  - only an allowlist of subcommands is permitted; food rm, person add/edit,
    and targets set for an adult-who-isn't-priyanka are refused;
  - writes are serialised with a lock; each run has a 30 s timeout.

Config (all via env):
  NUTRITION_TOKENS  JSON file {token: agent}, default ~/.hermes/secrets/nutrition_tokens.json (0600)
  NUTRITION_BIND    bind host, default 127.0.0.1
  NUTRITION_PORT    port, default 3420
  NUTRITION_ALLOW_IPS  comma-separated source-IP allowlist (empty = allow all)
  NUTRITION_DB      passed through to nutrition.py
Logs each request to ~/.hermes/state/nutrition_server.log.
"""
import json
import os
import subprocess
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUTRITION_PY = HERE / "nutrition.py"
RUN_TIMEOUT_S = 30

# Subcommands the client may invoke at all.
ALLOWED = {
    "log", "log-custom", "edit", "rm", "eaten", "day", "summary", "week",
    "gaps", "people-day", "food", "person", "targets", "body", "export",
}
# Subcommands that must carry an explicit --person.
REQUIRE_PERSON = {"log", "log-custom", "edit", "rm", "eaten", "body", "water"}
# Second-level allowlists.
FOOD_SUB_OK = {"find", "show", "add", "edit"}          # NOT rm
PERSON_SUB_OK = {"list"}                                # list only
# targets: show always ok; `set` only for a child person or priyanka.

_write_lock = threading.Lock()
WRITE_CMDS = {"log", "log-custom", "edit", "rm", "eaten", "body", "water",
              "food", "person", "targets"}


def _default_tokens_path():
    return Path.home() / ".hermes" / "secrets" / "nutrition_tokens.json"


def tokens_path():
    return Path(os.environ.get("NUTRITION_TOKENS") or _default_tokens_path())


def load_tokens():
    p = tokens_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def log_path():
    return Path.home() / ".hermes" / "state" / "nutrition_server.log"


def log_request(agent, argv, exit_code):
    try:
        lp = log_path()
        lp.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with lp.open("a") as fh:
            fh.write(json.dumps({"time": ts, "agent": agent,
                                 "argv": argv, "exit": exit_code}) + "\n")
    except OSError:
        pass


def allow_ips():
    raw = (os.environ.get("NUTRITION_ALLOW_IPS") or "").strip()
    return [ip.strip() for ip in raw.split(",") if ip.strip()]


def arg_value(argv, name):
    """Return the value of --name from argv, supporting --name V and --name=V."""
    pref = "--" + name + "="
    for i, a in enumerate(argv):
        if a == "--" + name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(pref):
            return a[len(pref):]
    return None


def strip_logged_by(argv):
    """Remove any client-supplied --logged-by / --logged_by (and =form)."""
    out = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ("--logged-by", "--logged_by"):
            skip = True  # drop its value too
            continue
        if a.startswith("--logged-by=") or a.startswith("--logged_by="):
            continue
        out.append(a)
    return out


def person_kind(person):
    """Look up a person's kind from the DB; None if unknown/no DB."""
    env = os.environ.get("NUTRITION_DB")
    path = Path(env) if env else (Path.home() / ".hermes" / "data" / "nutrition.db")
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            r = conn.execute("SELECT kind FROM people WHERE key=?",
                             (person.strip().lower(),)).fetchone()
            return r[0] if r else None
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def validate(argv):
    """Return (ok, http_status, message). Does not run anything."""
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return False, 400, "argv must be a non-empty list of strings"
    cmd = argv[0]
    if cmd not in ALLOWED:
        return False, 403, f"subcommand not allowed: {cmd!r}"

    if cmd == "food":
        sub = argv[1] if len(argv) > 1 else None
        if sub not in FOOD_SUB_OK:
            return False, 403, f"food {sub!r} not allowed (find/show/add/edit only)"
    if cmd == "person":
        sub = argv[1] if len(argv) > 1 else None
        if sub not in PERSON_SUB_OK:
            return False, 403, f"person {sub!r} not allowed (list only)"

    if cmd in REQUIRE_PERSON and not arg_value(argv, "person"):
        return False, 400, f"{cmd} requires an explicit --person"

    if cmd == "targets":
        sub = argv[1] if len(argv) > 1 else None
        if sub == "set":
            person = arg_value(argv, "person")
            if not person:
                return False, 400, "targets set requires an explicit --person"
            kind = person_kind(person)
            if not (person.strip().lower() == "priyanka" or kind == "child"):
                return False, 403, (
                    "targets set is only allowed for child persons or priyanka")
    return True, 200, "ok"


def run_nutrition(argv, agent):
    """Run nutrition.py with the agent forced via env; serialise writes."""
    argv = strip_logged_by(argv)
    env = dict(os.environ)
    env["NUTRITION_AGENT"] = agent
    cmd = [sys.executable, str(NUTRITION_PY)] + argv
    lock = _write_lock if argv[0] in WRITE_CMDS else None
    if lock:
        lock.acquire()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=RUN_TIMEOUT_S, env=env)
        return {"exit": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr}
    except subprocess.TimeoutExpired:
        return {"exit": 124, "stdout": "",
                "stderr": f"timed out after {RUN_TIMEOUT_S}s"}
    finally:
        if lock:
            lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "nutrition/2"

    def _send(self, status, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ip_ok(self):
        allow = allow_ips()
        if not allow:
            return True
        return self.client_address[0] in allow

    def log_message(self, fmt, *a):  # silence default stderr access log
        pass

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            self._send(200, {"ok": True, "schema": "2"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ip_ok():
            self._send(403, {"error": "source IP not allowed"})
            return
        if self.path.split("?")[0] != "/run":
            self._send(404, {"error": "not found"})
            return

        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        tokens = load_tokens()
        agent = tokens.get(token) if token else None
        if not agent:
            self._send(401, {"error": "invalid or missing bearer token"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "body must be JSON"})
            return
        argv = payload.get("argv")

        ok, status, msg = validate(argv)
        if not ok:
            log_request(agent, argv if isinstance(argv, list) else [], status)
            self._send(status, {"error": msg})
            return

        result = run_nutrition(argv, agent)
        log_request(agent, strip_logged_by(argv), result["exit"])
        self._send(200, result)


def main(argv=None):
    host = os.environ.get("NUTRITION_BIND", "127.0.0.1")
    port = int(os.environ.get("NUTRITION_PORT", "3420"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"nutrition_server on {host}:{port} "
          f"(tokens: {tokens_path()}, allow_ips: {allow_ips() or 'all'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
