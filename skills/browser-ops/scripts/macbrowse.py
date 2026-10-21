#!/usr/bin/env python3
"""macbrowse: drive a REAL browser (Firefox by default, or Safari/Chrome) on a Mac from the VPS.

It goes through the macOS accessibility API (cua-driver on the Mac). There is no CDP and no debugging
port, so sites see a normal person using a normal browser on a home IP. Use it for sites that reject
CDP-driven browsers (telcos, banks, credit bureaus, Amazon). It's a plain CLI, so cron jobs can use it.

How it works
  Each subcommand is one ssh round trip. A JSON request goes to the Mac on STDIN; the Mac-side helper
  (macbrowse_agent.py, copied to ~/.cache/macbrowse/agent.py whenever its sha256 differs, together
  with imac_sms_read.py) talks to cua-driver and answers with JSON on stdout.

Security rules (do not weaken)
  * Secrets and SMS codes NEVER appear in argv (local or remote), logs, stdout, exception text or
    temp files. `--secret item:field` is fetched from 1Password on the VPS into memory and travels
    only inside the stdin JSON. The Mac helper hands it to `cua-driver call` on stdin too.
  * `--sms-code` reads the code ON the Mac; it never travels to the VPS.
  * `type` prints only "typed N chars". Secure fields are shown as *** in `look`.
  * Don't log in to anything from the selftest; it only visits example.com / iana.org.

Known quirks
  * Firefox builds its web-content AX tree lazily: the first snapshot after a load can show an empty
    AXWebArea. The helper re-snapshots (up to 4 times, 1.5 s apart) until the web area has children.
  * A locked screen or sleeping display gives an empty tree / `ax_window_unresolved`. That's exit 4,
    "Mac screen locked or display asleep: unlock it". Nothing can be driven until someone unlocks.
  * Chat widgets ("Ask Jack" style) and cookie banners can cover controls. Element (AX) clicks still
    work under them, so `#N` / `text:` targets beat `xy:`. Pixel clicks are the fallback only.
  * Click x/y (`xy:X,Y`) is in the window SCREENSHOT pixel space (about 2x the point bounds on Retina).
  * Web-content typing goes in as a pixel focus-click plus typing in one call (background first, then
    foreground). Foreground briefly fronts the browser, then restores the previous app.
  * Firefox opens PDFs in its viewer instead of saving them. For `download`, click the viewer's save
    button or a link that forces a download.
  * The daemon auto-starts if it's down (`open -n -g -a CuaDriver --args serve`).

Exit codes: 0 ok, 1 error, 2 no such target / bad args, 3 timeout (download, SMS),
            4 screen locked / AX unavailable, 5 driver or ssh failure, 6 no browser window.
"""
import argparse, base64, hashlib, json, os, re, shlex, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
HOSTS = {
    "imac": os.environ.get("MACBROWSE_HOST", "sumeet@100.119.136.41"),
    "macbook": os.environ.get("MACBROWSE_MACBOOK_HOST", "sumeet@100.116.71.40"),
}
FILES = {"agent.py": os.path.join(HERE, "macbrowse_agent.py"), "imac_sms_read.py": os.path.join(HERE, "imac_sms_read.py")}
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=10",
       "-o", "ServerAliveCountMax=3"]
SCRATCH = os.path.expanduser("~/.hermes/cache/scratch")
OP_VAULT = os.environ.get("MACBROWSE_OP_VAULT", "Home Servers")

EPILOG = """examples:
  macbrowse.py open https://example.com
  macbrowse.py look --query "sign in"
  macbrowse.py text --max 3000
  macbrowse.py click 'text:^(sign in|log in)$'
  macbrowse.py click '#12' --wait 8
  macbrowse.py type 'text:user ?name|email' --secret 'Some Site:username'
  macbrowse.py type 'text:password' --secret 'Some Site:password' --enter
  macbrowse.py type 'text:code|verification' --sms-code --sms-grep 'sitename' --enter
  macbrowse.py key escape ; macbrowse.py key cmd+s
  macbrowse.py scroll down --amount 10
  macbrowse.py shot --out /tmp/page.png
  macbrowse.py download 'text:download pdf' --timeout 120
  macbrowse.py --host macbook --app Safari windows
  macbrowse.py selftest

targets: #N (from look) | text:REGEX (label/value, case-insensitive) | xy:X,Y (screenshot px)
         | focused (type only)
"""


class CliError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


# ---------------------------------------------------------------- transport
def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ssh(host, cmd, data, timeout):
    try:
        return subprocess.run(SSH + [host, cmd], input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CliError(5, "ssh to %s timed out after %ss" % (host, timeout))


def deploy(host):
    payload = json.dumps({n: base64.b64encode(open(p, "rb").read()).decode() for n, p in FILES.items()})
    code = ("import base64,json,os,sys;d=os.path.expanduser('~/.cache/macbrowse');os.makedirs(d,exist_ok=True);"
            "os.chmod(d,0o700);m=json.load(sys.stdin)\n"
            "for n,b in m.items():\n p=os.path.join(d,n);t=p+'.tmp';open(t,'wb').write(base64.b64decode(b));"
            "os.chmod(t,0o700);os.replace(t,p)")
    r = ssh(host, "/usr/bin/python3 -c %s" % shlex.quote(code), payload.encode(), 30)
    if r.returncode != 0:
        raise CliError(5, "could not copy the helper to %s: %s" % (host, r.stderr.decode()[-200:].strip()))


def agent(host, req, timeout=120):
    """One round trip. If the Mac's helper copy is missing/stale (exit 99), deploy and retry once."""
    checks = " && ".join('[ "$(shasum -a 256 "$d/%s" 2>/dev/null | cut -c1-64)" = "%s" ]' % (n, sha(p))
                         for n, p in FILES.items())
    cmd = 'd="$HOME/.cache/macbrowse"; { %s; } || exit 99; exec /usr/bin/python3 "$d/agent.py"' % checks
    data = json.dumps(req).encode()
    for attempt in (1, 2):
        r = ssh(host, cmd, data, timeout)
        if r.returncode == 99 and attempt == 1:
            deploy(host)
            continue
        break
    if r.returncode == 255:
        raise CliError(5, "ssh to %s failed: %s" % (host, r.stderr.decode()[-200:].strip()))
    try:
        res = json.loads(r.stdout.decode())
    except ValueError:
        raise CliError(5, "bad reply from Mac helper (rc=%s): %s" % (r.returncode, r.stderr.decode()[-200:].strip()))
    if not res.get("ok"):
        raise CliError(int(res.get("code") or 1), res.get("error") or "unknown error")
    return res


def op_secret(ref):
    """item:field from 1Password -> value in memory. The value is never printed or logged."""
    if ":" not in ref:
        raise CliError(2, "--secret must be ITEM:FIELD")
    item, field = ref.rsplit(":", 1)
    env = dict(os.environ)
    if "OP_SERVICE_ACCOUNT_TOKEN" not in env:
        try:
            env["OP_SERVICE_ACCOUNT_TOKEN"] = open(os.path.expanduser("~/.op_service_token")).read().strip()
        except OSError:
            raise CliError(1, "no 1Password service token (~/.op_service_token)")
    try:
        r = subprocess.run(["op", "item", "get", item, "--vault", OP_VAULT, "--fields", field, "--reveal"],
                           capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise CliError(1, "1Password CLI failed for that item")
    val = r.stdout.rstrip("\n")
    if r.returncode != 0 or not val:
        raise CliError(1, "1Password lookup failed for the field %r of that item" % field)
    return val


# ---------------------------------------------------------------- output
def emit(args, res, human):
    if args.json:
        res = {k: v for k, v in res.items() if k != "png_b64"}
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(human)


def tu(res):
    return "title: %s\nurl:   %s" % (res.get("title") or "", res.get("url") or "(not shown)")


# ---------------------------------------------------------------- commands
def base(args, op, **kw):
    req = {"op": op, "app": args.app, "t_start": time.time()}
    req.update(kw)
    return req


def cmd_windows(args):
    res = agent(args.host, base(args, "windows"), 60)
    lines = ["%-22s %s" % (w["app"], w["title"]) for w in res["windows"]]
    if res.get("locked"):
        lines.append("(screen is LOCKED)")
    emit(args, res, "\n".join(lines))


def cmd_open(args):
    res = agent(args.host, base(args, "open", url=args.url, wait=args.wait), args.wait + 90)
    emit(args, res, tu(res))
    return res


def cmd_look(args):
    res = agent(args.host, base(args, "look", query=args.query, limit=args.limit), 120)
    lines = [tu(res), "%d actionable elements%s" % (res["count"], " (showing %d)" % len(res["elements"])
                                                    if len(res["elements"]) < res["count"] else "")]
    lines += [e["line"] for e in res["elements"]]
    emit(args, res, "\n".join(lines))
    return res


def cmd_text(args):
    res = agent(args.host, base(args, "text", max=args.max), 120)
    emit(args, res, tu(res) + "\n---\n" + res["text"])
    return res


def cmd_click(args):
    res = agent(args.host, base(args, "click", target=args.target, wait=args.wait), args.wait + 120)
    emit(args, res, "clicked %s (%s)\n%s" % (res.get("clicked"), res.get("via"), tu(res)))
    return res


def cmd_type(args):
    kw = {"target": args.target, "enter": args.enter}
    if args.secret:
        kw["text"] = op_secret(args.secret)
    elif args.sms_code:
        kw.update(sms_code=True, sms_grep=args.sms_grep, sms_minutes=args.sms_minutes, sms_wait=90)
    else:
        kw["text"] = args.text
    res = agent(args.host, base(args, "type", **kw), 240)
    kw.clear()
    emit(args, res, "typed %d chars%s" % (res["typed"], " + return" if args.enter else ""))


def cmd_key(args):
    res = agent(args.host, base(args, "key", combo=args.combo), 60)
    emit(args, res, "pressed %s\ntitle: %s" % (res["key"], res.get("title") or ""))


def cmd_scroll(args):
    res = agent(args.host, base(args, "scroll", direction=args.direction, amount=args.amount), 90)
    emit(args, res, "scrolled %s %d" % (res["direction"], res["amount"]))


def default_shot():
    os.makedirs(SCRATCH, exist_ok=True)
    return os.path.join(SCRATCH, "macbrowse_%s.png" % time.strftime("%Y%m%d-%H%M%S"))


def cmd_shot(args):
    res = agent(args.host, base(args, "shot"), 120)
    out = os.path.expanduser(args.out or default_shot())
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    data = base64.b64decode(res["png_b64"])
    with open(out, "wb") as f:
        f.write(data)
    os.chmod(out, 0o600)
    res.update(path=out, bytes=len(data))
    emit(args, res, out)
    return res


def cmd_download(args):
    res = agent(args.host, base(args, "download", target=args.target, timeout=args.timeout), args.timeout + 150)
    outdir = os.path.expanduser(args.out or os.path.join(SCRATCH, "downloads"))
    os.makedirs(outdir, exist_ok=True)
    local = os.path.join(outdir, os.path.basename(res["path"]))
    r = ssh(args.host, "cat -- %s" % shlex.quote(res["path"]), b"", max(120, args.timeout))
    if r.returncode != 0 or len(r.stdout) != res["size"]:
        raise CliError(5, "copy from Mac failed (got %d of %d bytes)" % (len(r.stdout), res["size"]))
    with open(local, "wb") as f:
        f.write(r.stdout)
    os.chmod(local, 0o600)
    res.update(local=local)
    emit(args, res, "%s  %d bytes  %r" % (local, res["size"], res["head"]))


def cmd_selftest(args):
    """Live test on a harmless page. Only visits example.com and iana.org; logs in nowhere."""
    j, args.json = args.json, False
    results = []

    def step(name, fn):
        try:
            ok, info = fn()
        except CliError as e:
            ok, info = False, "exit %d: %s" % (e.code, e.msg)
        results.append(ok)
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, info), flush=True)
        return ok

    st = {}

    def s_open():
        st["open"] = r = agent(args.host, base(args, "open", url="https://example.com", wait=12), 120)
        return "Example Domain" in r["title"], "title=%r url=%r" % (r["title"], r["url"])

    def s_look():
        r = agent(args.host, base(args, "look", query="", limit=200), 120)
        hits = [e for e in r["elements"] if e["role"] == "AXLink"
                and re.search("More information|Learn more", e.get("label") or "", re.I)]
        st["link"] = hits[0] if hits else None
        return bool(hits), (hits[0]["line"] if hits else "links: %s" % [e["line"] for e in r["elements"]][:8])

    def s_text():
        r = agent(args.host, base(args, "text", max=6000), 120)
        return "documentation examples" in r["text"], "%d chars: %r" % (len(r["text"]), r["text"][:70])

    def s_click():
        r = agent(args.host, base(args, "click", target="text:More information|Learn more", wait=10), 150)
        before = st["open"]
        changed = r["title"] != before["title"] or (r["url"] and r["url"] != before["url"])
        return bool(changed), "via=%s title=%r url=%r" % (r.get("via"), r["title"], r["url"])

    def s_shot():
        args.out = None
        res = agent(args.host, base(args, "shot"), 120)
        data = base64.b64decode(res["png_b64"])
        out = default_shot()
        with open(out, "wb") as f:
            f.write(data)
        os.chmod(out, 0o600)
        return data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 10240, "%s %d bytes" % (out, len(data))

    step("1 open https://example.com", s_open) and step("2 look finds the More-information link", s_look)
    if len(results) == 2:
        step("3 text contains the body copy (headings are not exposed by Firefox AX via cua-driver)", s_text)
        step("4 click link changes title/url", s_click)
    step("5 shot is a PNG > 10 KB", s_shot)
    args.json = j
    print("selftest: %s (%d/%d)" % ("PASS" if all(results) and len(results) == 5 else "FAIL",
                                    sum(results), 5))
    return 0 if all(results) and len(results) == 5 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="macbrowse.py", description=__doc__.split("\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="imac", help="imac | macbook | user@ip (default imac; env MACBROWSE_HOST)")
    ap.add_argument("--app", default="Firefox", help="Firefox | Safari | Chrome (default Firefox)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("open", help="open URL in the browser (new tab) and wait for the title")
    p.add_argument("url")
    p.add_argument("--wait", type=float, default=12)
    p.set_defaults(fn=cmd_open)
    p = sp.add_parser("look", help="list actionable page elements as #idx role \"label\" =\"value\"")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=80)
    p.set_defaults(fn=cmd_look)
    p = sp.add_parser("text", help="page text without vision")
    p.add_argument("--max", type=int, default=6000)
    p.set_defaults(fn=cmd_text)
    p = sp.add_parser("click", help="click #N | text:REGEX | xy:X,Y")
    p.add_argument("target")
    p.add_argument("--wait", type=float, default=3)
    p.set_defaults(fn=cmd_click)
    p = sp.add_parser("type", help="focus a target and type text / a 1Password secret / an SMS code")
    p.add_argument("target", help="#N | text:REGEX | xy:X,Y | focused")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", help="literal (non-secret) text")
    g.add_argument("--secret", metavar="ITEM:FIELD", help="1Password item (id or title) and field")
    g.add_argument("--sms-code", action="store_true", help="newest SMS code, read on the Mac")
    p.add_argument("--sms-grep", default="", help="regex the SMS must match (sender or body)")
    p.add_argument("--sms-minutes", type=int, default=5, help="Messages look-back window")
    p.add_argument("--enter", action="store_true", help="press return afterwards")
    p.set_defaults(fn=cmd_type)
    p = sp.add_parser("key", help="press a key or combo: escape, return, tab, cmd+s ...")
    p.add_argument("combo")
    p.set_defaults(fn=cmd_key)
    p = sp.add_parser("scroll", help="scroll the page")
    p.add_argument("direction", choices=["down", "up"])
    p.add_argument("--amount", type=int, default=5)
    p.set_defaults(fn=cmd_scroll)
    p = sp.add_parser("shot", help="window screenshot, copied to the VPS")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_shot)
    p = sp.add_parser("download", help="click a target and fetch the new file from ~/Downloads")
    p.add_argument("target")
    p.add_argument("--timeout", type=float, default=90)
    p.add_argument("--out", help="local dir (default ~/.hermes/cache/scratch/downloads/)")
    p.set_defaults(fn=cmd_download)
    p = sp.add_parser("windows", help="list on-screen windows")
    p.set_defaults(fn=cmd_windows)
    p = sp.add_parser("selftest", help="live test against example.com")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    args.host = HOSTS.get(args.host, args.host)
    try:
        rc = args.fn(args)
        return rc if isinstance(rc, int) else 0
    except CliError as e:
        if args.json:
            print(json.dumps({"ok": False, "code": e.code, "error": e.msg}))
        else:
            print("error: %s" % e.msg, file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
