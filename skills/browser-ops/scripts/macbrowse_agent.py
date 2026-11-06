#!/usr/bin/env python3
"""Mac-side helper for macbrowse.py. Do not run by hand.

macbrowse.py copies this file to ~/.cache/macbrowse/agent.py on the Mac and runs it over ssh.
Protocol: ONE JSON request on stdin -> ONE JSON reply on stdout.
  reply = {"ok": true, ...} or {"ok": false, "code": N, "error": "one line"}
Secrets (text to type, SMS codes) only ever live in this process's memory and in the JSON fed
to `cua-driver call <tool>` on ITS stdin. They are never put in argv, files, logs or the reply.
Python 3.9 stdlib only (macOS /usr/bin/python3).
"""
import base64, difflib, json, os, re, subprocess, sys, time

CUA = os.path.expanduser("~/.local/bin/cua-driver")
HOME = os.path.expanduser("~/.cache/macbrowse")
CACHE = os.path.join(HOME, "snap.json")
SMS = os.path.join(HOME, "imac_sms_read.py")
DOWNLOADS = os.path.expanduser("~/Downloads")
PARTIAL = (".part", ".crdownload", ".download", ".tmp")
LOCKED = "Mac screen locked or display asleep: unlock it"
ACTIONABLE = {"AXLink", "AXButton", "AXTextField", "AXTextArea", "AXSearchField", "AXSecureTextField",
              "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXComboBox", "AXMenuItem", "AXMenuButton",
              "AXTab", "AXSlider", "AXDisclosureTriangle", "AXIncrementor", "AXSwitch", "AXToggle"}
PREFERRED = ["AXLink", "AXButton", "AXMenuItem", "AXCheckBox", "AXRadioButton"]
EDITABLE = {"AXTextField", "AXTextArea", "AXSearchField", "AXSecureTextField", "AXComboBox"}
TEXT_ROLES = {"AXStaticText", "AXHeading"}
APP_NAMES = {"chrome": "Google Chrome", "google chrome": "Google Chrome", "safari": "Safari", "firefox": "Firefox"}


class Fail(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


# ---------------------------------------------------------------- driver plumbing
def cua(tool, args, timeout=60):
    """Call a cua-driver tool. Args go on stdin (never argv: they may hold typed text)."""
    try:
        r = subprocess.run([CUA, "call", tool], input=json.dumps(args), capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Fail(5, "cua-driver %s timed out after %ss" % (tool, timeout))
    out = r.stdout.strip()
    try:
        d = json.loads(out)
    except ValueError:
        d = None
    if not isinstance(d, dict):
        # Error text from the driver can echo the request; never pass it through for text-bearing tools.
        msg = "(details withheld)" if tool == "type_text" else (out or r.stderr.strip())[:300].replace("\n", " ")
        raise Fail(5, "cua-driver %s failed: %s" % (tool, msg))
    return d


def ensure_daemon():
    try:
        d = cua("list_windows", {}, timeout=20)
        if "windows" in d:
            return d
    except Fail:
        pass
    subprocess.run(["open", "-n", "-g", "-a", "CuaDriver", "--args", "serve"], capture_output=True, timeout=20)
    time.sleep(6)
    d = cua("list_windows", {}, timeout=30)
    if "windows" not in d:
        raise Fail(5, "cua-driver daemon not answering after auto-start")
    return d


def keep_awake(seconds=900):
    """Hold the display awake while a browsing session is active, so the Mac doesn't sleep and lock mid-task.
    Same effect as a playing video. Each call refreshes a single `caffeinate -d -u` lease; nothing is changed
    in the Mac's security settings, and it expires on its own `seconds` after the last command."""
    try:
        subprocess.run(["pkill", "-f", "caffeinate -d -u -t"], capture_output=True, timeout=5)
        subprocess.Popen(["caffeinate", "-d", "-u", "-t", str(int(seconds))], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


def screen_locked():
    keep_awake()
    try:
        out = subprocess.run(["ioreg", "-n", "Root", "-d1"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False
    return '"CGSSessionScreenIsLocked"=Yes' in out


def app_name(app):
    return APP_NAMES.get(app.lower(), app)


def pick_window(windows, app):
    name = app_name(app).lower()
    mine = [w for w in windows if w.get("app_name", "").lower() == name]
    on = [w for w in mine if w.get("is_on_screen") and w["bounds"]["width"] > 200 and w["bounds"]["height"] > 200]
    titled = [w for w in on if (w.get("title") or "").lower() == name]
    best = titled or sorted(on, key=lambda w: -w["bounds"]["width"] * w["bounds"]["height"])
    return best[0] if best else None


def find_window(app, windows=None):
    w = pick_window(windows if windows is not None else ensure_daemon()["windows"], app)
    if not w:
        if screen_locked():
            raise Fail(4, LOCKED)
        raise Fail(6, "no on-screen %s window (open one with: macbrowse open URL)" % app_name(app))
    return w


def window_title(app, wid):
    for w in cua("list_windows", {}, timeout=20).get("windows", []):
        if w.get("window_id") == wid:
            return w.get("title") or ""
    return ""


# ---------------------------------------------------------------- snapshots
def web_area(elements):
    """(index_into_list, element) of the main AXWebArea: the largest one."""
    best, area = None, -1
    for i, e in enumerate(elements):
        if e.get("role") == "AXWebArea":
            f = e.get("frame") or {}
            a = (f.get("w") or 0) * (f.get("h") or 0)
            if a > area:
                best, area = i, a
    return best


def inside_web(elements, wi):
    """Elements after the web area in DFS order whose depth is greater (= its subtree)."""
    if wi is None:
        return []
    d0 = elements[wi].get("depth", 0)
    out = []
    for e in elements[wi + 1:]:
        if e.get("depth", 0) <= d0:
            break
        out.append(e)
    return out


def raw_snapshot(pid, wid, shot_file=None):
    args = {"pid": pid, "window_id": wid, "include_screenshot": bool(shot_file)}
    if shot_file:
        args["screenshot_out_file"] = shot_file
    return cua("get_window_state", args, timeout=90)


def snapshot(app, shot_file=None, need_web=True):
    """Snapshot the browser window. Retries for Firefox's lazy AX activation. Saves the cache."""
    w = find_window(app)
    pid, wid = w["pid"], w["window_id"]
    d = {}
    for attempt in range(4):
        d = raw_snapshot(pid, wid, shot_file)
        els = d.get("elements") or []
        deg = str(d.get("degraded_reason") or "")
        wi = web_area(els)
        good = els and not deg.startswith("ax_window_unresolved")
        if good and (not need_web or (wi is not None and inside_web(els, wi))):
            break
        time.sleep(1.5)
    els = d.get("elements") or []
    deg = str(d.get("degraded_reason") or "")
    if not els or deg.startswith("ax_window_unresolved"):
        if screen_locked() or deg.startswith("ax_window_unresolved") or not els:
            raise Fail(4, LOCKED)
    wi = web_area(els)
    snap = {"pid": pid, "window_id": wid, "bounds": w["bounds"], "snapshot_id": d.get("snapshot_id"),
            "title": w.get("title") or "", "elements": els, "web_index": wi, "ts": time.time()}
    snap["url"] = address_bar(snap)
    save_cache(snap)
    if shot_file:
        snap["shot_file"] = d.get("screenshot_file_path") or shot_file
    return snap


def save_cache(snap):
    os.makedirs(HOME, exist_ok=True)
    keep = {k: snap[k] for k in ("pid", "window_id", "bounds", "snapshot_id", "title", "url", "ts")}
    keep["elements"] = [slim(e) for e in web_elements(snap)]
    keep["last_action_ts"] = (load_cache() or {}).get("last_action_ts")
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(keep, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CACHE)


def load_cache():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except Exception:
        return None


def slim(e):
    return {k: e.get(k) for k in ("element_index", "element_token", "role", "label", "value", "frame",
                                  "parent_index", "depth")}


def web_elements(snap):
    return inside_web(snap["elements"], snap["web_index"])


def address_bar(snap):
    """URL from the browser chrome: Firefox AXComboBox value; Safari/Chrome address AXTextField."""
    web = {id(e) for e in web_elements(snap)}
    cands = []
    for e in snap["elements"]:
        if id(e) in web or e.get("role") not in ("AXComboBox", "AXTextField"):
            continue
        v = e.get("value")
        if not isinstance(v, str) or not v.strip():
            continue
        lab = (e.get("label") or "").lower()
        score = 2 if e.get("role") == "AXComboBox" else 0
        score += 2 if re.search(r"address|url|search or enter|location", lab) else 0
        score += 1 if re.match(r"^(https?://|about:|file:|data:|[\w-]+\.[\w.-]+(/|$))", v.strip()) else 0
        cands.append((score, v.strip()))
    if not cands:
        return ""
    cands.sort(key=lambda c: -c[0])
    return cands[0][1] if cands[0][0] > 0 else ""


def page_title(snap):
    if snap.get("title"):
        return snap["title"]
    wi = snap.get("web_index")
    return (snap["elements"][wi].get("label") or "") if wi is not None else ""


def actionable(snap):
    return [e for e in web_elements(snap) if e.get("element_index") is not None and e.get("role") in ACTIONABLE]


def describe(e):
    role = (e.get("role") or "").replace("AX", "", 1)
    s = "#%s %s" % (e.get("element_index"), role)
    lab, val = (e.get("label") or "").strip(), e.get("value")
    if lab:
        s += ' "%s"' % lab[:80]
    if isinstance(val, str) and val.strip() and val.strip() != lab:
        s += ' ="%s"' % (val.strip()[:60] if e.get("role") != "AXSecureTextField" else "***")
    return s


def page_text(snap, limit):
    out, seen, n = [], set(), 0
    for e in web_elements(snap):
        if e.get("role") not in TEXT_ROLES:
            continue
        t = e.get("value") if isinstance(e.get("value"), str) and e.get("value").strip() else e.get("label")
        t = re.sub(r"\s+", " ", (t or "")).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
        n += len(t) + 1
        if n >= limit:
            break
    return "\n".join(out)[:limit]


# ---------------------------------------------------------------- targets
def by_index(snap):
    return {e.get("element_index"): e for e in snap["elements"] if e.get("element_index") is not None}


def ancestor_actionable(snap, e):
    idx = by_index(snap)
    seen = 0
    cur = e
    while cur is not None and seen < 30:
        if cur.get("role") in ACTIONABLE:
            return cur
        cur = idx.get(cur.get("parent_index"))
        seen += 1
    return e


def text_label(e):
    return " ".join(str(x) for x in (e.get("label"), e.get("value")) if isinstance(x, str) and x.strip())


def match_text(snap, rx):
    try:
        pat = re.compile(rx, re.I)
    except re.error as ex:
        raise Fail(2, "bad regex: %s" % ex)
    hits = []
    for e in web_elements(snap):
        if e.get("role") in TEXT_ROLES or e.get("role") in ACTIONABLE:
            if pat.search(text_label(e)):
                t = ancestor_actionable(snap, e)
                if t.get("element_index") is not None and t not in hits:
                    hits.append(t)
    if not hits:
        labels = [text_label(e) for e in actionable(snap) if text_label(e)]
        plain = re.sub(r"[^\w ]+", " ", rx).strip().lower()
        close = sorted(set(labels), key=lambda l: -difflib.SequenceMatcher(None, plain, l.lower()).ratio())[:5]
        raise Fail(2, "no element matches /%s/; closest: %s" % (rx, "; ".join('"%s"' % c[:60] for c in close)
                                                                   or "(page has no actionable elements)"))

    def rank(e):
        r = e.get("role")
        f = e.get("frame") or {}
        return (PREFERRED.index(r) if r in PREFERRED else len(PREFERRED), f.get("y", 1e9), f.get("x", 1e9))
    return sorted(hits, key=rank)[0]


def resolve(snap, target):
    """-> ("el", element) or ("xy", (x, y)) or ("focused", None)."""
    t = target.strip()
    if t == "focused":
        return "focused", None
    if t.startswith("xy:"):
        try:
            x, y = (float(v) for v in t[3:].split(","))
        except ValueError:
            raise Fail(2, "xy target must be xy:X,Y")
        return "xy", (x, y)
    if t.startswith("#"):
        try:
            i = int(t[1:])
        except ValueError:
            raise Fail(2, "bad index target %s" % t)
        e = by_index(snap).get(i)
        if not e:
            raise Fail(2, "no element #%d in the current page snapshot (run look again)" % i)
        return "el", e
    if t.startswith("text:"):
        return "el", match_text(snap, t[5:])
    raise Fail(2, "target must be #N, text:REGEX, xy:X,Y or focused")


def fresh_for_index(app, target):
    """For #N: reuse the look snapshot when the page is unchanged, re-resolve by role+label otherwise."""
    cached = load_cache()
    snap = snapshot(app)
    if cached and target.strip().startswith("#"):
        try:
            i = int(target.strip()[1:])
        except ValueError:
            return snap
        old = next((e for e in cached["elements"] if e.get("element_index") == i), None)
        new = by_index(snap).get(i)
        if old and (not new or (new.get("role"), new.get("label")) != (old.get("role"), old.get("label"))):
            same = [e for e in actionable(snap) if (e.get("role"), e.get("label")) == (old.get("role"), old.get("label"))]
            if same:
                of = old.get("frame") or {}
                same.sort(key=lambda e: abs((e.get("frame") or {}).get("y", 0) - of.get("y", 0)))
                return dict(snap, _override={i: same[0]})
            raise Fail(2, "element #%d (%s) is gone from the page; run look again" % (i, describe(old)))
    return snap


def pixel_scale(snap):
    """Screenshot px per point, from a tiny PNG header read of a fresh capture."""
    tmp = os.path.join(HOME, "scale.png")
    try:
        raw_snapshot(snap["pid"], snap["window_id"], tmp)
        with open(tmp, "rb") as f:
            head = f.read(24)
        width = int.from_bytes(head[16:20], "big")
        return width / float(snap["bounds"]["width"]) if width else 2.0
    except Exception:
        return 2.0
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def px_center(snap, e, scale):
    f = e.get("frame") or {}
    b = snap["bounds"]
    cx, cy = f.get("x", 0) + f.get("w", 0) / 2.0, f.get("y", 0) + f.get("h", 0) / 2.0
    # Frames are screen points; convert to window-local screenshot pixels.
    return (cx - b["x"]) * scale, (cy - b["y"]) * scale


def ok(d):
    return isinstance(d, dict) and not d.get("error") and d.get("isError") is not True and d.get("ok") is not False


def do_click(snap, kind, val):
    pid, wid = snap["pid"], snap["window_id"]
    base = {"pid": pid, "window_id": wid}
    if kind == "xy":
        r = cua("click", dict(base, x=val[0], y=val[1]))
        if not ok(r):
            r = cua("click", dict(base, x=val[0], y=val[1], delivery_mode="foreground"))
        return "px", r
    e = val
    if e.get("element_token"):
        r = cua("click", dict(base, element_token=e["element_token"]))
        if ok(r):
            return "ax", r
    if e.get("element_index") is not None and snap.get("snapshot_id"):
        r = cua("click", dict(base, element_index=e["element_index"], snapshot_id=snap["snapshot_id"]))
        if ok(r):
            return "ax", r
    x, y = px_center(snap, e, pixel_scale(snap))
    r = cua("click", dict(base, x=x, y=y))
    if not ok(r):
        r = cua("click", dict(base, x=x, y=y, delivery_mode="foreground"))
    return "px", r


def settle(app, wid, old_title, wait):
    """Wait up to `wait` s for the title to change (min 1 s), then let the page render briefly."""
    t0 = time.time()
    time.sleep(min(1.0, wait))
    changed = False
    while time.time() - t0 < wait:
        if window_title(app, wid) != old_title:
            changed = True
            break
        time.sleep(0.5)
    if changed:
        time.sleep(1.0)
    return changed


def mark_action():
    c = load_cache() or {}
    c["last_action_ts"] = time.time()
    try:
        with open(CACHE, "w") as f:
            json.dump(c, f)
    except OSError:
        pass


def target_of(snap, target):
    kind, val = resolve(snap, target)
    ov = snap.get("_override") or {}
    if kind == "el" and target.strip().startswith("#") and int(target.strip()[1:]) in ov:
        val = ov[int(target.strip()[1:])]
    return kind, val


def after(app, snap, old_title, wait, extra=None):
    changed = settle(app, snap["window_id"], old_title, wait)
    s2 = snapshot(app)
    r = {"ok": True, "title": page_title(s2), "url": s2["url"], "title_changed": changed}
    r.update(extra or {})
    return r


# ---------------------------------------------------------------- typing
def sms_code(req):
    """Poll Messages on this Mac for a code newer than the command start (or the last click)."""
    start = float(req.get("t_start") or time.time())
    last = (load_cache() or {}).get("last_action_ts") or 0
    since = last if 0 < start - last < 600 else start
    since -= 2
    deadline = time.time() + float(req.get("sms_wait", 90))
    minutes = max(2, int(req.get("sms_minutes", 5)))
    if not os.path.exists(SMS):
        raise Fail(5, "imac_sms_read.py not deployed")
    while True:
        argv = ["/usr/bin/python3", SMS, "--minutes", str(minutes)]
        if req.get("sms_grep"):
            argv += ["--grep", req["sms_grep"]]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise Fail(5, "SMS reader failed (Full Disk Access for sshd?)")
        for line in r.stdout.splitlines():
            m = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \| [^|]* \| (.*)$", line)
            if not m:
                continue
            ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
            if ts < since:
                break  # rows are newest first
            c = re.search(r"(?<!\d)(\d{4,8})(?!\d)", m.group(2))
            if c:
                return c.group(1)
        if time.time() > deadline:
            raise Fail(3, "no new SMS code within %ss" % int(req.get("sms_wait", 90)))
        time.sleep(3)


def field_len(app, e):
    """Length of an editable field's value in a fresh snapshot (None if unknown)."""
    s = snapshot(app)
    f = e.get("frame") or {}
    for c in web_elements(s):
        if c.get("role") == e.get("role") and c.get("label") == e.get("label") and (c.get("frame") or {}) == f:
            v = c.get("value")
            return len(v) if isinstance(v, str) else None
    return None


def do_type(app, snap, kind, val, text, enter):
    base = {"pid": snap["pid"], "window_id": snap["window_id"]}
    landed = None
    if kind == "focused":
        r = cua("type_text", dict(base, text=text))
        if not ok(r):
            r = cua("type_text", dict(base, text=text, delivery_mode="foreground"))
        landed = ok(r)
    elif kind == "xy":
        r = cua("type_text", dict(base, text=text, x=val[0], y=val[1]))
        if not ok(r):
            r = cua("type_text", dict(base, text=text, x=val[0], y=val[1], delivery_mode="foreground"))
        landed = ok(r)
    else:
        e = val
        before = e.get("value")
        before = len(before) if isinstance(before, str) else None
        scale = pixel_scale(snap)
        x, y = px_center(snap, e, scale)
        tries = [dict(base, text=text, x=x, y=y), dict(base, text=text, x=x, y=y, delivery_mode="foreground")]
        for args in tries:
            r = cua("type_text", args)
            time.sleep(0.4)
            now = field_len(app, e)
            if not ok(r):
                # Background key delivery can report type_text_incomplete (delivered_chars 0) even though
                # every character landed (TikTok password field, 2026-10-23). Retrying then typed it twice.
                if now is not None and before is not None and now != before:
                    landed = True
                    break
                continue
            if now is None or before is None or now != before:
                landed = True  # changed, or unverifiable (no value exposed): never risk typing twice
                break
            landed = False
            snap = snapshot(app)
            base = {"pid": snap["pid"], "window_id": snap["window_id"]}
    if not landed:
        raise Fail(5, "typing did not land in the target field")
    if enter:
        cua("press_key", dict(base, key="return"))
    mark_action()
    return {"ok": True, "typed": len(text)}


# ---------------------------------------------------------------- downloads
def list_downloads():
    out = {}
    try:
        for n in os.listdir(DOWNLOADS):
            p = os.path.join(DOWNLOADS, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if os.path.isfile(p):
                out[n] = (st.st_mtime, st.st_size)
    except OSError:
        pass
    return out


def wait_download(t0, before, timeout):
    deadline = time.time() + timeout
    sizes = {}
    while time.time() < deadline:
        cur = list_downloads()
        names = set(cur)
        for n, (mt, sz) in sorted(cur.items(), key=lambda kv: -kv[1][0]):
            if n.startswith(".") or n.lower().endswith(PARTIAL):
                continue
            if n in before and before[n] == (mt, sz):
                continue
            if mt < t0 - 2:
                continue
            if any(n + suf in names for suf in PARTIAL) or sz == 0:
                continue
            if sizes.get(n) == sz:
                p = os.path.join(DOWNLOADS, n)
                with open(p, "rb") as f:
                    head = f.read(4)
                return {"path": p, "size": sz, "head": head.decode("latin-1")}
            sizes[n] = sz
        time.sleep(1.0)
    raise Fail(3, "no new complete file in ~/Downloads within %ss" % timeout)


# ---------------------------------------------------------------- ops
def op_windows(req):
    ws = ensure_daemon()["windows"]
    rows = [{"app": w.get("app_name"), "title": w.get("title") or "", "pid": w.get("pid"),
             "window_id": w.get("window_id")} for w in ws
            if w.get("is_on_screen") and w["bounds"]["width"] > 200 and w["bounds"]["height"] > 100]
    return {"ok": True, "windows": rows, "locked": screen_locked()}


def op_open(req):
    app, url, wait = req["app"], req["url"], float(req.get("wait", 12))
    if screen_locked():
        raise Fail(4, LOCKED)
    ws = ensure_daemon()["windows"]
    w = pick_window(ws, app)
    old = (w.get("title") or "") if w else None
    r = subprocess.run(["open", "-a", app_name(app), url], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise Fail(5, "open failed: %s" % r.stderr.strip()[:200])
    t0 = time.time()
    changed = False
    while time.time() - t0 < wait:
        time.sleep(0.5)
        w2 = pick_window(cua("list_windows", {}, timeout=20).get("windows", []), app)
        if w2 and (old is None or (w2.get("title") or "") != old):
            changed = True
            break
    if changed:
        time.sleep(1.0)
    snap = snapshot(app)
    return {"ok": True, "title": page_title(snap), "url": snap["url"], "title_changed": changed}


def op_look(req):
    snap = snapshot(req["app"])
    els = actionable(snap)
    q = (req.get("query") or "").lower()
    if q:
        els = [e for e in els if q in text_label(e).lower()]
    lim = int(req.get("limit", 80))
    return {"ok": True, "title": page_title(snap), "url": snap["url"], "count": len(els),
            "elements": [dict(slim(e), line=describe(e)) for e in els[:lim]]}


def op_text(req):
    snap = snapshot(req["app"])
    return {"ok": True, "title": page_title(snap), "url": snap["url"],
            "text": page_text(snap, int(req.get("max", 6000)))}


def op_click(req):
    app = req["app"]
    snap = fresh_for_index(app, req["target"])
    kind, val = target_of(snap, req["target"])
    if kind == "focused":
        raise Fail(2, "click needs #N, text:REGEX or xy:X,Y")
    old = window_title(app, snap["window_id"])
    how, r = do_click(snap, kind, val)
    if not ok(r):
        raise Fail(5, "click failed: %s" % json.dumps(r)[:200])
    mark_action()
    return after(app, snap, old, float(req.get("wait", 3)),
                 {"clicked": describe(val) if kind == "el" else "xy:%g,%g" % val, "via": how})


def op_type(req):
    app = req["app"]
    text = req.get("text")
    if req.get("sms_code"):
        text = sms_code(req)
    if not isinstance(text, str) or not text:
        raise Fail(2, "nothing to type")
    snap = fresh_for_index(app, req["target"]) if req["target"].strip() != "focused" else snapshot(app, need_web=False)
    kind, val = target_of(snap, req["target"])
    return do_type(app, snap, kind, val, text, bool(req.get("enter")))


def op_key(req):
    w = find_window(req["app"])
    if screen_locked():
        raise Fail(4, LOCKED)
    parts = [p.strip().lower() for p in req["combo"].split("+") if p.strip()]
    if not parts:
        raise Fail(2, "empty key combo")
    base = {"pid": w["pid"], "window_id": w["window_id"]}
    mods = {"cmd", "command", "shift", "option", "alt", "ctrl", "control", "fn"}
    if len(parts) == 1:
        args = dict(base, key=parts[0])
        tool = "press_key"
    else:
        if any(p not in mods for p in parts[:-1]):
            raise Fail(2, "combo must be modifiers + one key, e.g. cmd+s")
        args = dict(base, keys=parts)
        tool = "hotkey"
    r = cua(tool, args)
    if not ok(r):
        r = cua(tool, dict(args, delivery_mode="foreground"))
    if not ok(r):
        raise Fail(5, "%s failed: %s" % (tool, json.dumps(r)[:200]))
    mark_action()
    time.sleep(0.5)
    return {"ok": True, "key": req["combo"], "title": window_title(req["app"], w["window_id"])}


def op_scroll(req):
    snap = snapshot(req["app"])
    base = {"pid": snap["pid"], "window_id": snap["window_id"], "direction": req["direction"],
            "amount": max(1, min(50, int(req.get("amount", 5))))}
    wi = snap["web_index"]
    web = snap["elements"][wi] if wi is not None else {}
    args = dict(base, element_token=web["element_token"]) if web.get("element_token") else base
    r = cua("scroll", args)
    if not ok(r) and args is not base:
        r = cua("scroll", base)
    if not ok(r):
        r = cua("scroll", dict(base, delivery_mode="foreground"))
    if not ok(r):
        raise Fail(5, "scroll failed: %s" % json.dumps(r)[:200])
    return {"ok": True, "direction": req["direction"], "amount": base["amount"]}


def op_shot(req):
    os.makedirs(HOME, exist_ok=True)
    path = os.path.join(HOME, "shot.png")
    snap = snapshot(req["app"], shot_file=path, need_web=False)
    p = snap.get("shot_file") or path
    try:
        with open(os.path.expanduser(p), "rb") as f:
            data = f.read()
    except OSError:
        raise Fail(4, LOCKED if screen_locked() else "screenshot was not captured (Screen Recording permission?)")
    finally:
        try:
            os.remove(os.path.expanduser(p))
        except OSError:
            pass
    return {"ok": True, "title": page_title(snap), "url": snap["url"], "png_b64": base64.b64encode(data).decode()}


def op_download(req):
    app = req["app"]
    t0 = time.time()
    before = list_downloads()
    snap = fresh_for_index(app, req["target"])
    kind, val = target_of(snap, req["target"])
    if kind == "focused":
        raise Fail(2, "download needs #N, text:REGEX or xy:X,Y")
    how, r = do_click(snap, kind, val)
    if not ok(r):
        raise Fail(5, "click failed: %s" % json.dumps(r)[:200])
    mark_action()
    got = wait_download(t0, before, float(req.get("timeout", 90)))
    got.update(ok=True, clicked=describe(val) if kind == "el" else "xy")
    return got


OPS = {"windows": op_windows, "open": op_open, "look": op_look, "text": op_text, "click": op_click,
       "type": op_type, "key": op_key, "scroll": op_scroll, "shot": op_shot, "download": op_download}


def main():
    try:
        req = json.loads(sys.stdin.read() or "{}")
        req.setdefault("app", "Firefox")
        fn = OPS.get(req.get("op"))
        if not fn:
            raise Fail(2, "unknown op %r" % req.get("op"))
        res = fn(req)
    except Fail as f:
        res = {"ok": False, "code": f.code, "error": f.msg}
    except Exception as ex:  # never echo request contents
        res = {"ok": False, "code": 1, "error": "agent error: %s" % type(ex).__name__}
    sys.stdout.write(json.dumps(res))


if __name__ == "__main__":
    main()
