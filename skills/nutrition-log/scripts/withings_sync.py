#!/usr/bin/env python3
"""Withings → nutrition DB body sync (stdlib only).

  withings_sync.py auth-url        print the one-time consent URL (user opens on phone)
  withings_sync.py status          token present? last measure?
  withings_sync.py sync [--days N] pull weight / fat% / fat-free mass / muscle / bone / water (default 14 d)
                                   into ~/.hermes/data/nutrition.db `body` table (source=withings), print summary

Tokens: ~/.hermes/secrets/withings_tokens.json (0600), refreshed automatically (access 3 h, refresh 1 y,
refresh token ROTATES on every refresh, so always write the new one back).
App creds: ~/.hermes/secrets/withings_app.json (0600). 1Password: "Withings Developer App (Mankoo Household Health Sync)".
"""
import json, os, sqlite3, sys, time, urllib.parse, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
SEC = os.path.expanduser("~/.hermes/secrets")
APP = os.path.join(SEC, "withings_app.json")
TOK = os.path.join(SEC, "withings_tokens.json")
DB = os.environ.get("NUTRITION_DB", os.path.expanduser("~/.hermes/data/nutrition.db"))
API = "https://wbsapi.withings.net"
# meastype -> (metric, unit)
TYPES = {1: "weight_kg", 6: "body_fat_pct", 5: "fat_free_mass_kg", 8: "fat_mass_kg",
         76: "muscle_mass_kg", 88: "bone_mass_kg", 77: "body_water_kg", 11: "heart_rate_bpm",
         170: "visceral_fat_index", 226: "bmr_kcal"}


def _post(path, params, token=None):
    req = urllib.request.Request(API + path, data=urllib.parse.urlencode(params).encode())
    if token:
        req.add_header("Authorization", "Bearer " + token)
    return json.load(urllib.request.urlopen(req, timeout=30))


def _save_tok(b):
    b["obtained_at"] = int(time.time())
    fd = os.open(TOK, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(b, f)


def access_token():
    if not os.path.exists(TOK):
        sys.exit("no withings token yet: run `auth-url` and have Sumeet approve")
    t = json.load(open(TOK))
    if time.time() < t["obtained_at"] + int(t.get("expires_in", 10800)) - 300:
        return t["access_token"]
    a = json.load(open(APP))
    r = _post("/v2/oauth2", {"action": "requesttoken", "grant_type": "refresh_token",
                             "client_id": a["client_id"], "client_secret": a["client_secret"],
                             "refresh_token": t["refresh_token"]})
    if r.get("status") != 0:
        sys.exit(f"refresh failed: status {r.get('status')} {r.get('error')}: re-consent needed (auth-url)")
    _save_tok(r["body"])
    return r["body"]["access_token"]


def auth_url():
    a = json.load(open(APP))
    q = {"response_type": "code", "client_id": a["client_id"], "scope": "user.metrics,user.activity",
         "redirect_uri": a["redirect_uri"], "state": a["state"]}
    print("https://account.withings.com/oauth2_user/authorize2?" + urllib.parse.urlencode(q))


def sync(days=14):
    tok = access_token()
    r = _post("/measure", {"action": "getmeas", "meastypes": ",".join(map(str, TYPES)), "category": 1,
                           "startdate": int(time.time()) - days * 86400, "enddate": int(time.time())}, tok)
    if r.get("status") != 0:
        sys.exit(f"getmeas failed: status {r.get('status')} {r.get('error')}")
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS body(id INTEGER PRIMARY KEY, person TEXT NOT NULL DEFAULT 'sumeet', day TEXT, metric TEXT, value REAL, source TEXT, at TEXT, UNIQUE(person,day,metric,source))")
    n, latest = 0, {}
    for g in sorted(r["body"].get("measuregrps", []), key=lambda g: g["date"]):
        dt = datetime.fromtimestamp(g["date"], TZ)
        for m in g["measures"]:
            k = TYPES.get(m["type"])
            if not k:
                continue
            v = round(m["value"] * 10 ** m["unit"], 2)
            # one value per day per metric: the latest weigh-in of the day wins
            # body is per-person since household v2 (2026-10-13): UNIQUE(person,day,metric,source)
            con.execute("INSERT INTO body(person,day,metric,value,source,at) VALUES(?,?,?,?,?,?) "
                        "ON CONFLICT(person,day,metric,source) DO UPDATE SET value=excluded.value, at=excluded.at",
                        ("sumeet", dt.date().isoformat(), k, v, "withings", dt.isoformat()))
            latest[k] = (dt.date().isoformat(), v)
            n += 1
    con.commit()
    print(f"withings: {n} measures over {days} d")
    for k, (d, v) in sorted(latest.items()):
        print(f"  {k}: {v} ({d})")
    return latest


def status():
    print("app creds:", os.path.exists(APP), "| token:", os.path.exists(TOK))
    if os.path.exists(DB):
        con = sqlite3.connect(DB)
        for row in con.execute("SELECT metric,value,day FROM body WHERE source='withings' AND metric IN ('weight_kg','body_fat_pct') ORDER BY day DESC LIMIT 4"):
            print(" ", row)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "auth-url":
        auth_url()
    elif cmd == "sync":
        d = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 14
        sync(d)
    else:
        status()
