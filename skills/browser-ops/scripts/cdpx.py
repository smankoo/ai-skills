#!/usr/bin/env python3
"""cdpx — one-shot CLI over Chrome DevTools (trusted, human-like input via human_cdp.Tab).

Endpoint: --ep vps (default, :9222) | imac (:19334, auto ssh tunnel) | imac2 (:19335) | http://host:port
          or env CDPX_EP. TAB = URL/title substring (case-insensitive) | exact target id | @last.
If websocket-client is missing, cdpx re-execs itself via `uv run --with websocket-client`.

  cdpx.py tabs
  cdpx.py open https://example.com --wait 30          # prints id + title, remembers @last
  cdpx.py nav @last https://example.com/login
  cdpx.py js @last 'document.title'                   # expression
  cdpx.py js amazon 'const a=[...document.links]; return a.length'   # statement body
  cdpx.py js @last 'await fetch("/x").then(r=>r.status)'             # async
  cdpx.py js @last -f snippet.js        |   echo 'location.href' | cdpx.py js @last -
  cdpx.py text @last -n 2000 --grep 'order|total'
  cdpx.py fields @last [--all]                         # #idx TAG type name aria "text" value= sel
  cdpx.py click @last --idx 3 | --sel '#go' | --text '^Sign in$' | --xy 400,300
  printf %s "$PW" | cdpx.py type @last --idx 5 - --enter   # secret never in argv / output
  cdpx.py type @last --sel '#q' 'running shoes' --no-clear
  cdpx.py select @last --sel '#country' canada         # option value or visible text
  cdpx.py key @last Escape                             # Enter Tab Escape ArrowDown Backspace ...
  cdpx.py scroll @last 800
  cdpx.py wait @last --text 'Thank you' | --sel '#done' | --url 'checkout' [--timeout 20]
  cdpx.py shot @last /tmp/p.png [--full]               # full height capped at 7900 px
  cdpx.py close @last
  cdpx.py selftest                                     # against vps; prints PASS n/n

Exit codes: 0 ok, 1 error, 2 tab not found, 3 endpoint unreachable, 4 type did not land, 5 wait timeout.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

try:
    import websocket  # noqa: F401
except ImportError:
    if os.environ.get("CDPX_REEXEC"):
        sys.exit("cdpx: websocket-client unavailable (try: uv run --with websocket-client python3 cdpx.py ...)")
    os.environ["CDPX_REEXEC"] = "1"
    os.execvp("uv", ["uv", "run", "-q", "--with", "websocket-client", "python3", os.path.abspath(__file__), *sys.argv[1:]])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_cdp import Tab  # noqa: E402

EPS = {"vps": "http://127.0.0.1:9222", "imac": "http://127.0.0.1:19334", "imac2": "http://127.0.0.1:19335"}
TUNNELS = {"imac": (19334, 9334), "imac2": (19335, 9335)}
CACHE = os.path.expanduser("~/.cache/cdpx")
KEYS = {"Enter": (13, "\r"), "Tab": (9, None), "Escape": (27, None), "Backspace": (8, None), "Delete": (46, None),
        "ArrowDown": (40, None), "ArrowUp": (38, None), "ArrowLeft": (37, None), "ArrowRight": (39, None),
        "Home": (36, None), "End": (35, None), "PageDown": (34, None), "PageUp": (33, None), "Space": (32, " ")}


class Exit(Exception):
    def __init__(self, code, msg=""): super().__init__(msg); self.code = code


# ---------------------------------------------------------------- endpoint / tab resolution
def _alive(ep):
    try: urllib.request.urlopen(ep + "/json/version", timeout=2).read(); return True
    except Exception: return False


def endpoint(alias):
    ep = EPS.get(alias, alias).rstrip("/")
    if not re.match(r"https?://", ep): raise Exit(1, f"bad endpoint: {alias}")
    if _alive(ep): return ep
    if alias in TUNNELS:
        lp, rp = TUNNELS[alias]
        subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-fN", "-L",
                        f"{lp}:127.0.0.1:{rp}", "sumeet@100.119.136.41"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        for _ in range(6):
            if _alive(ep): return ep
            time.sleep(0.5)
    raise Exit(3, f"endpoint unreachable: {ep}")


def _last_path(alias): return os.path.join(CACHE, "last_" + re.sub(r"[^\w.-]", "_", alias))


def pages(ep):
    return [t for t in json.loads(urllib.request.urlopen(ep + "/json", timeout=10).read()) if t.get("type") == "page"]


def find_target(ep, alias, spec):
    ts = pages(ep)
    if spec == "@last":
        try: spec = open(_last_path(alias)).read().strip()
        except OSError: raise Exit(2, "no @last recorded (use `cdpx open` first)")
        hits = [t for t in ts if t["id"] == spec]
    else:
        hits = [t for t in ts if t["id"] == spec] or [
            t for t in ts if spec.lower() in t.get("url", "").lower() or spec.lower() in t.get("title", "").lower()]
    if not hits: raise Exit(2, f"tab not found: {spec}")
    if len(hits) > 1: print(f"cdpx: {len(hits)} tabs match {spec!r}; using first ({hits[0]['id']})", file=sys.stderr)
    return hits[0]


def attach(a):
    t = find_target(a.ep_url, a.ep, a.tab)
    tab = Tab(t["webSocketDebuggerUrl"]); tab.target_id = t["id"]; tab.endpoint = a.ep_url
    return tab


# ---------------------------------------------------------------- js helpers
def top_level_return(s):
    """True if `return` appears outside any ()/[]/{} nesting, strings, and comments."""
    depth, i, n = 0, 0, len(s)
    while i < n:
        c = s[i]
        if c in "'\"`":
            i += 1
            while i < n and s[i] != c: i += 2 if s[i] == "\\" else 1
        elif s.startswith("//", i): i = s.find("\n", i) % (n + 1) or n
        elif s.startswith("/*", i): i = (s.find("*/", i + 2) + 2) or n
        elif c in "([{": depth += 1
        elif c in ")]}": depth -= 1
        elif depth == 0 and s.startswith("return", i) and not (i and (s[i - 1].isalnum() or s[i - 1] in "_$")) \
                and not s[i + 6:i + 7].isalnum(): return True
        i += 1
    return False


def wrap(expr):
    s = expr.strip()
    if s.startswith("{") or top_level_return(s):
        return f"(async()=>{{{s}\n}})()", False
    return s, "await" in s  # replMode allows top-level await in plain expressions


def evaluate(t, expr):
    src, repl = wrap(expr)
    params = dict(expression=src, returnByValue=True, awaitPromise=True)
    if repl: params["replMode"] = True
    r = t.cdp("Runtime.evaluate", **params)
    if "exceptionDetails" in r:
        d = r["exceptionDetails"]
        raise Exit(1, (d.get("exception") or {}).get("description") or d.get("text") or "JS exception")
    return r.get("result", {})


def jsv(t, expr): return evaluate(t, expr).get("value")


def target_css(a):
    if getattr(a, "idx", None) is not None: return f'[data-cdpx="{a.idx}"]'
    if getattr(a, "sel", None): return a.sel
    raise Exit(1, "need --sel or --idx")


def q(css): return f"document.querySelector({json.dumps(css)})"


def safe_url(t):
    for _ in range(10):
        try: return t.url()
        except Exception: time.sleep(0.5)
    return "?"


FIELDS_JS = r"""
(cap) => {
  document.querySelectorAll('[data-cdpx]').forEach(e => e.removeAttribute('data-cdpx'));
  const S = 'input:not([type=hidden]),select,textarea,button,a[href],[role=button],[role=combobox],[contenteditable=""],[contenteditable=true]';
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const uniq = sel => { try { return document.querySelectorAll(sel).length === 1; } catch (_) { return false; } };
  const cl = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const out = []; let i = 0;
  for (const e of document.querySelectorAll(S)) {
    if (!vis(e)) continue;
    if (cap && i >= cap) break;
    e.setAttribute('data-cdpx', i);
    const tag = e.tagName.toLowerCase(), nm = e.getAttribute('name');
    let sel = `[data-cdpx="${i}"]`;
    if (e.id && uniq('#' + CSS.escape(e.id))) sel = '#' + CSS.escape(e.id);
    else if (nm && uniq(`${tag}[name="${nm}"]`)) sel = `${tag}[name="${nm}"]`;
    const txt = cl(e.innerText || e.placeholder || (tag === 'input' && ['submit','button'].includes(e.type) ? e.value : ''), 40);
    const val = ('value' in e && !['submit','button'].includes(e.type)) ?
      (e.type === 'password' ? '*'.repeat(e.value.length) : cl(e.value, 30)) : '';
    out.push(`#${i} ${e.tagName} ${e.getAttribute('type') || e.getAttribute('role') || '-'} ${nm || e.id || '-'} ` +
             `${cl(e.getAttribute('aria-label'), 30) || '-'} ${JSON.stringify(txt)} value=${JSON.stringify(val)} ${sel}`);
    i++;
  }
  return out.join('\n');
}"""


# ---------------------------------------------------------------- commands
def cmd_tabs(a):
    for t in pages(a.ep_url): print(f"{t['id']}  {t.get('title', '')[:60]}  {t.get('url', '')[:100]}")


def cmd_open(a):
    t = Tab.new(a.ep_url, a.url)
    if a.wait:
        end = time.time() + a.wait
        while time.time() < end and t.js("document.readyState") != "complete": time.sleep(0.5)
    os.makedirs(CACHE, exist_ok=True)
    with open(_last_path(a.ep), "w") as f: f.write(t.target_id)
    print(t.target_id, t.js("document.title") or "")


def cmd_nav(a):
    t = attach(a); t.navigate(a.url); print(safe_url(t))


def cmd_js(a):
    if a.file: expr = open(a.file).read()
    elif a.expr == "-": expr = sys.stdin.read()
    elif a.expr: expr = a.expr
    else: raise Exit(1, "need EXPR, -f FILE or -")
    r = evaluate(attach(a), expr)
    if r.get("type") == "undefined" and "value" not in r: return
    v = r.get("value")
    print(v if isinstance(v, str) and not a.json else json.dumps(v, ensure_ascii=False, indent=None))


def cmd_text(a):
    txt = attach(a).text(a.n if not a.grep else 10 ** 8)
    if not a.grep: print(txt); return
    lines, rx, keep = txt.splitlines(), re.compile(a.grep, re.I), set()
    for i, l in enumerate(lines):
        if rx.search(l): keep.update(range(max(0, i - 1), min(len(lines), i + 2)))
    out, prev = [], None
    for i in sorted(keep):
        if prev is not None and i != prev + 1: out.append("--")
        out.append(lines[i]); prev = i
    print("\n".join(out)[:a.n])


def cmd_fields(a):
    print(jsv(attach(a), f"({FIELDS_JS})({0 if a.all else 80})") or "")


def cmd_click(a):
    t = attach(a)
    try:
        if a.xy: x, y = (float(v) for v in a.xy.split(",")); t.click_xy(x, y)
        elif a.text: t.click_text(a.text)
        else: t.click_sel(target_css(a))
    except LookupError: raise Exit(1, "click target not found")
    time.sleep(1); print(safe_url(t))


def cmd_type(a):
    s = sys.stdin.read().rstrip("\n") if a.text == "-" else a.text
    t, css = attach(a), target_css(a)
    if not jsv(t, f"!!{q(css)}"): raise Exit(1, f"element not found: {css}")
    try: t.type_sel(css, s, clear=not a.no_clear)
    except LookupError: raise Exit(1, f"element not found: {css}")
    k, typ = jsv(t, f"(() => {{ const e={q(css)}; return [String(e.value ?? e.innerText ?? '').length, e.type || ''] }})()")
    if a.enter: t.enter()
    print(f"typed {len(s)} chars value_len={k}")
    if k == 0 and typ != "password": raise Exit(4, "typed text did not land")


def cmd_select(a):
    r = jsv(attach(a), f"""(() => {{ const e={q(target_css(a))}; if (!e || !e.options) return null;
      const v={json.dumps(a.value.lower())};
      const o=[...e.options].find(o => o.value.toLowerCase() === v) || [...e.options].find(o => o.text.trim().toLowerCase() === v);
      if (!o) return null; e.value = o.value;
      e.dispatchEvent(new Event('input', {{bubbles: true}})); e.dispatchEvent(new Event('change', {{bubbles: true}}));
      return o.text.trim(); }})()""")
    if r is None: raise Exit(1, "select or option not found")
    print(r)


def cmd_key(a):
    t, k = attach(a), a.key
    if k == "Enter": t.enter()
    elif k in KEYS:
        vk, txt = KEYS[k]; t.key(" " if k == "Space" else k, code=k, vk=vk, text=txt)
    elif len(k) == 1: t.key(k, code="Key" + k.upper() if k.isalpha() else k, vk=ord(k.upper()), text=k)
    else: t.key(k)
    print("ok")


def cmd_scroll(a):
    attach(a).wheel(a.dy); print("ok")


def cmd_wait(a):
    t, end = attach(a), time.time() + a.timeout
    while True:
        try:
            if a.text and re.search(a.text, t.text(10 ** 8), re.I): break
            if a.sel and jsv(t, f"!!{q(a.sel)}"): break
            if a.url and re.search(a.url, t.url() or ""): break
        except Exit: raise
        except Exception: pass
        if time.time() > end: raise Exit(5, "wait timeout")
        time.sleep(0.5)
    print("ok", safe_url(t))


def _png_size(b): return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def cmd_shot(a):
    import base64
    t, p = attach(a), {"format": "png"}
    if a.full:
        m = t.cdp("Page.getLayoutMetrics"); cs = m.get("cssContentSize") or m["contentSize"]
        w, h = cs["width"], min(cs["height"], 7900)
        p.update(captureBeyondViewport=True, clip={"x": 0, "y": 0, "width": w, "height": h, "scale": 1})
    b = base64.b64decode(t.cdp("Page.captureScreenshot", **p)["data"])
    pw, ph = _png_size(b)
    if a.full and ph > 7900:  # high-DPR display: shrink so pixel height fits
        p["clip"]["scale"] = 7900 / ph * 0.999
        b = base64.b64decode(t.cdp("Page.captureScreenshot", **p)["data"]); pw, ph = _png_size(b)
    with open(a.out, "wb") as f: f.write(b)
    print(a.out, f"{pw}x{ph}")


def cmd_close(a):
    t = find_target(a.ep_url, a.ep, a.tab)
    urllib.request.urlopen(urllib.request.Request(a.ep_url + "/json/close/" + t["id"], method="PUT"), timeout=10).read()
    print("closed", t["id"])


# ---------------------------------------------------------------- selftest
def cmd_selftest(a):
    me, tok = os.path.abspath(__file__), f"cdpx-selftest-{os.getpid()}"
    html = (f"<title>{tok}</title><input id=name placeholder='Your name'>"
            "<select id=color><option value=r>Red</option><option value=g>Green</option><option value=b>Blue</option></select>"
            "<button id=go onclick=\"out.textContent='Hello '+document.getElementById('name').value+' '+color.value\">Go</button>"
            "<div id=out></div><div>alpha</div><div>beta</div><div>gamma</div>")
    url = "data:text/html," + urllib.parse.quote(html)
    shot = f"/tmp/{tok}.png"

    def run(*args, stdin=None):
        r = subprocess.run([sys.executable, me, "--ep", "vps", *args], input=stdin, capture_output=True, text=True, timeout=90)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    steps, tid = [], None

    def check(name, cond, info=""):
        steps.append(name)
        if not cond: raise Exit(1, f"FAIL step {len(steps)} {name}: {info}")

    try:
        rc, out, err = run("open", url); tid = out.split()[0] if out else None
        check("open", rc == 0 and tok in out, out + err)
        rc, out, err = run("tabs"); check("tabs", rc == 0 and tid in out, out + err)
        rc, out, err = run("js", tok, "1+2"); check("js expression", out == "3", out + err)
        rc, out, err = run("js", "@last", "const a = 2; return a * 5"); check("js statement", out == "10", out + err)
        rc, out, err = run("js", "@last", "await new Promise(r => setTimeout(() => r('ok'), 100))")
        check("js async", out == "ok", out + err)
        rc, out, err = run("js", "@last", "-", stdin="return {a: [1, 'x']}"); check("js stdin", out == '{"a": [1, "x"]}', out + err)
        rc, out, err = run("js", "@last", "nosuchvar.x"); check("js exception exit 1", rc == 1 and "nosuchvar" in err, err)
        rc, out, err = run("fields", "@last")
        btn = next((l.split()[0][1:] for l in out.splitlines() if " BUTTON " in l), None)
        check("fields", rc == 0 and "#name" in out and '"Your name"' in out and btn is not None, out + err)
        rc, out, err = run("type", "@last", "--sel", "#name", "-", stdin="Ada\n")
        check("type", rc == 0 and out == "typed 3 chars value_len=3", out + err)
        rc, out, err = run("select", "@last", "--sel", "#color", "blue"); check("select", out == "Blue", out + err)
        rc, out, err = run("click", "@last", "--idx", btn); check("click", rc == 0 and out.startswith("data:"), out + err)
        rc, out, err = run("wait", "@last", "--text", "Hello Ada b", "--timeout", "5"); check("wait", rc == 0, out + err)
        rc, out, err = run("wait", "@last", "--sel", "#nope", "--timeout", "1"); check("wait timeout exit 5", rc == 5, err)
        rc, out, err = run("text", "@last", "--grep", "^beta$")
        check("text --grep", out.splitlines() == ["alpha", "beta", "gamma"], out + err)
        rc, out, err = run("shot", "@last", shot, "--full")
        ok = rc == 0 and os.path.exists(shot) and open(shot, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
        check("shot", ok and re.search(r"\d+x\d+$", out), out + err)
        rc, out, err = run("js", "no-such-tab-zzz", "1"); check("tab not found exit 2", rc == 2, err)
        rc, out, err = run("close", "@last"); check("close", rc == 0, out + err)
        rc, out, err = run("tabs"); check("no tabs left", tid not in out, out); tid = None
    except Exit as e:
        print(e, file=sys.stderr); return 1
    finally:
        if tid:
            try: urllib.request.urlopen(urllib.request.Request(EPS["vps"] + "/json/close/" + tid, method="PUT"), timeout=10)
            except Exception: pass
        if os.path.exists(shot): os.remove(shot)
    print(f"PASS {len(steps)}/{len(steps)}")
    return 0


# ---------------------------------------------------------------- argparse
def main(argv=None):
    ap = argparse.ArgumentParser(prog="cdpx", description="One-shot Chrome DevTools CLI (see module docstring).")
    ap.add_argument("--ep", default=os.environ.get("CDPX_EP", "vps"), help="vps | imac | imac2 | http://host:port")
    sp = ap.add_subparsers(dest="cmd", required=True)

    def sub(name, fn, tab=True):
        p = sp.add_parser(name); p.set_defaults(fn=fn)
        if tab: p.add_argument("tab")
        return p

    def target(p):
        p.add_argument("--sel"); p.add_argument("--idx", type=int)

    sub("tabs", cmd_tabs, tab=False)
    p = sub("open", cmd_open, tab=False); p.add_argument("url"); p.add_argument("--wait", type=float, default=0)
    p = sub("nav", cmd_nav); p.add_argument("url")
    p = sub("js", cmd_js); p.add_argument("expr", nargs="?"); p.add_argument("-f", "--file"); p.add_argument("--json", action="store_true")
    p = sub("text", cmd_text); p.add_argument("-n", type=int, default=4000); p.add_argument("--grep")
    p = sub("fields", cmd_fields); p.add_argument("--all", action="store_true")
    p = sub("click", cmd_click); target(p); p.add_argument("--text"); p.add_argument("--xy")
    p = sub("type", cmd_type); target(p); p.add_argument("text")
    p.add_argument("--no-clear", action="store_true"); p.add_argument("--enter", action="store_true")
    p = sub("select", cmd_select); target(p); p.add_argument("value")
    p = sub("key", cmd_key); p.add_argument("key")
    p = sub("scroll", cmd_scroll); p.add_argument("dy", type=int)
    p = sub("wait", cmd_wait); p.add_argument("--text"); p.add_argument("--sel"); p.add_argument("--url")
    p.add_argument("--timeout", type=float, default=20)
    p = sub("shot", cmd_shot); p.add_argument("out"); p.add_argument("--full", action="store_true")
    sub("close", cmd_close)
    sub("selftest", cmd_selftest, tab=False)
    a = ap.parse_args(argv)
    if a.cmd == "selftest": a.ep = "vps"
    if a.cmd == "wait" and not (a.text or a.sel or a.url): ap.error("wait needs --text, --sel or --url")
    if a.cmd == "click" and not (a.sel or a.idx is not None or a.text or a.xy): ap.error("click needs a target")
    try:
        a.ep_url = endpoint(a.ep)
        return a.fn(a) or 0
    except Exit as e:
        if str(e): print(f"cdpx: {e}", file=sys.stderr)
        return e.code
    except Exception as e:
        print(f"cdpx: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
