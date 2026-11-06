#!/usr/bin/env python3
"""jev — fast typed decisions from TypeSafe Jev via the OpenRouter Decisions API.

Jev is NOT a chat model. It answers questions you define about a `state` and returns
typed answers + calibrated probabilities in ~0.2s for ~$0.00003/call:
  noul   -> yes/no, returns P(yes)
  choice -> one of N labelled options, returns probabilities + confidence
  score  -> position on an ordered scale, returns a weighted score + confidence

Use as a CLI or import as a library (`sys.path.insert(0, <skill>/scripts); import jev`).

Subcommands
  ask    ad-hoc questions about a state
  rank   score N candidates (links, search results, files, options) against a goal
  page   classify a web page's state (content / login / captcha / bot wall / error ...)
  gate   should this automated message interrupt the user? (exit 10 = mute)
  raw    send a full request JSON (stdin) and print the response

Key: $OPENROUTER_API_KEY, else ~/.config/jev/openrouter_key (0600).
Every call is appended to ~/.cache/jev/calls.jsonl (question names, answers, cost; no state text).
"""
import argparse, datetime, json, os, sys, time, urllib.error, urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")  # pinned; thresholds tuned on 1.13
KEY_FILE = os.path.expanduser("~/.config/jev/openrouter_key")
LOG_FILE = os.path.expanduser("~/.cache/jev/calls.jsonl")
STATE_CHAR_CAP = 90_000  # ~32k-token state budget with headroom


class JevError(RuntimeError):
    pass


# ---------------------------------------------------------------- core
def _key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k.strip()
    if os.path.exists(KEY_FILE):
        return open(KEY_FILE).read().strip()
    raise JevError(f"no OpenRouter key: set OPENROUTER_API_KEY or write it to {KEY_FILE}")


def _log(entry):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def decide(state, questions, model=None, timeout=20, retries=2, tag=None):
    """Low-level call. `questions` = {name: {type, instructions, criteria}}. Returns the
    response dict (answers, usage, model). Raises JevError on failure."""
    if isinstance(state, str) and len(state) > STATE_CHAR_CAP:
        state = state[:STATE_CHAR_CAP]
    body = json.dumps({"model": model or DEFAULT_MODEL, "state": state, "questions": questions}).encode()
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            "Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
            "X-Title": "jev-cli"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            if "answers" not in d:
                raise JevError(f"unexpected response: {str(d)[:300]}")
            _log({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "tag": tag,
                  "ms": int((time.time() - t0) * 1000), "model": d.get("model"),
                  "cost": d.get("usage", {}).get("cost"),
                  "answers": {k: {kk: vv for kk, vv in v.items() if kk != "legend"}
                              for k, v in d["answers"].items()}})
            return d
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            last = JevError(f"HTTP {e.code}: {msg}")
            if e.code not in (429, 500, 502, 503, 504):
                raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = JevError(f"network: {e}")
        time.sleep(0.6 * (attempt + 1))
    raise last or JevError("unknown failure")


def noul(instructions, true=None, false=None):
    q = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true or "Yes.", "false": false or "No."}
    return q


def choice(instructions, options):
    """options: {label: description}"""
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def score(instructions, levels):
    """levels: ordered list, lowest first"""
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def ask(state, **questions):
    """ask(state, is_bug=noul("..."), team=choice("...", {...})) -> {name: answer_dict}"""
    return decide(state, questions)["answers"]


# ---------------------------------------------------------------- rank
def rank(goal, candidates, context=None, top=None, criterion=None):
    """Score each candidate against `goal` in ONE call (parallel nouls).
    candidates: list of str or dict (e.g. {"text":..., "href":...}).
    Returns list of {"i", "p", "candidate"} sorted by p desc."""
    if not candidates:
        return []
    cands = list(candidates)[:200]
    state = {"goal": goal, "candidates": {f"c{i}": c for i, c in enumerate(cands)}}
    if context:
        state["context"] = context
    crit = criterion or "Following / choosing this candidate is a direct, useful step toward the goal."
    qs = {f"c{i}": {"type": "noul",
                    "instructions": {"question": "Is this candidate a good match for the goal?",
                                     "candidate": f"candidates.c{i}"},
                    "criteria": {"true": crit,
                                 "false": "Irrelevant, a distraction, navigation chrome, an ad, or only loosely related."}}
          for i in range(len(cands))}
    ans = decide(state, qs, tag="rank")["answers"]
    out = sorted(({"i": i, "p": ans[f"c{i}"]["noul"], "candidate": cands[i]} for i in range(len(cands))),
                 key=lambda r: -r["p"])
    return out[:top] if top else out


# ---------------------------------------------------------------- page
PAGE_KINDS = {
    "content": "The real page content the visitor wanted is shown (article, product, listing, results, form).",
    "login_wall": "Must sign in / create an account before seeing the content.",
    "captcha": "A CAPTCHA or human-verification puzzle (reCAPTCHA, hCaptcha, Turnstile checkbox, press-and-hold).",
    "bot_block": "Access denied / blocked / 'unusual traffic' / Cloudflare or Akamai challenge / rate limited.",
    "cookie_or_modal": "A cookie banner, region picker, newsletter or age-gate modal is covering the content.",
    "error": "404, 500, empty page, 'something went wrong', or the page failed to load.",
    "paywall": "Subscription or paywall blocks the content.",
}


def page(text, goal=None, url=None, title=None, signals=None):
    """Classify page state; if goal given also ask whether the page satisfies it.
    Returns {"kind", "kind_conf", "kind_probs", "has_answer"(p or None)}."""
    state = {"url": url, "title": title, "visible_text": (text or "")[:40_000]}
    if signals:  # e.g. {"iframes": [src...], "inputs": [...], "buttons": [...]} — CAPTCHA widgets live in iframes
        state["dom_signals"] = signals
    qs = {"kind": choice("What state is this web page in, from the visitor's point of view?", PAGE_KINDS)}
    if goal:
        state["goal"] = goal
        qs["has_answer"] = noul("Does the visible page text already contain what the goal needs?",
                                "The needed information / element is present on this page.",
                                "It is not here; more navigation, search or interaction is needed.")
    a = decide(state, qs, tag="page")["answers"]
    return {"kind": a["kind"]["choice"], "kind_conf": a["kind"].get("confidence"),
            "kind_probs": a["kind"].get("probabilities"),
            "has_answer": a["has_answer"]["noul"] if "has_answer" in a else None}


# ---------------------------------------------------------------- browser helpers
# Paste-free use inside browser_exec:
#   import sys, os; sys.path.insert(0, os.path.expanduser("~/.ai-skills/skills/jev/scripts")); import jev
#   links = js(jev.LINKS_JS); best = jev.rank(goal, links, top=5)
#   st = jev.page(js(jev.TEXT_JS), goal, url=js("location.href"), title=js("document.title"), signals=js(jev.SIGNALS_JS))
LINKS_JS = """(() => [...document.querySelectorAll('a[href],button,[role=button],[role=link]')]
 .filter(a => a.offsetParent !== null)
 .map((a, i) => ({i, text: (a.innerText || a.getAttribute('aria-label') || a.title || '').trim().replace(/\\s+/g,' ').slice(0, 100),
                  href: a.href || null, tag: a.tagName.toLowerCase()}))
 .filter(l => l.text.length > 1).slice(0, 200))()"""
TEXT_JS = "document.body ? document.body.innerText.slice(0, 40000) : ''"
SIGNALS_JS = """(() => ({
 iframes: [...document.querySelectorAll('iframe')].map(f => (f.src || '').slice(0, 120)).filter(Boolean).slice(0, 10),
 inputs: [...document.querySelectorAll('input,select,textarea')].filter(e => e.type !== 'hidden')
          .map(e => (e.type || '') + ':' + (e.name || e.id || e.placeholder || '')).slice(0, 25),
 buttons: [...document.querySelectorAll('button,input[type=submit]')].map(b => (b.innerText || b.value || '').trim().slice(0, 40))
          .filter(Boolean).slice(0, 20)}))()"""


def page_from(js_fn, goal=None):
    """One-liner for browser_exec: jev.page_from(js, goal)."""
    return page(js_fn(TEXT_JS) or "", goal, url=js_fn("location.href"), title=js_fn("document.title"),
                signals=js_fn(SIGNALS_JS))


def links_from(js_fn, goal, top=5):
    """One-liner for browser_exec: ranked visible links/buttons for a goal."""
    return rank(goal, js_fn(LINKS_JS) or [], context={"url": js_fn("location.href"), "title": js_fn("document.title")}, top=top)


# ---------------------------------------------------------------- gate
GATE_KINDS = {
    "routine_ok": "Everything healthy / nothing changed; at most trivial auto-cleanup.",
    "needs_action": "Asks the user to decide, approve, reply, pay, or fix something.",
    "failure": "Reports an error, outage, failed check, or degraded service.",
    "security": "Security or integrity alert: file-integrity changes, rootkit scan, intrusion, attacks.",
    "new_info": "A briefing, reminder, digest, or genuinely new finding.",
}
NEVER_MUTE = ("failure", "needs_action", "security")


def gate(text, job=None, threshold=0.2):
    """Should an automated report interrupt the user? Fails OPEN on error (send=True).
    Threshold 0.2 was tuned on 60 real cron reports: routine all-clears score 0.05-0.09,
    anything with real signal >= 0.37."""
    state = {"report": text[:60_000]}
    if job:
        state["job_name"] = job
    qs = {
        "worth_sending": noul(
            "The user gets this automated report as a phone notification. Is it worth interrupting them?",
            "Something needs their attention or decision, something failed or is degraded, there is "
            "genuinely new information, it is a reminder/briefing they asked for, or it is any security "
            "or integrity alert (intrusion, filesystem changes, rootkit, attacks).",
            "A routine all-clear or status heartbeat saying everything is fine, where any automatic "
            "fixes were minor housekeeping that needs nothing from them."),
        "kind": choice("What kind of report is this?", GATE_KINDS),
    }
    try:
        a = decide(state, qs, tag=f"gate:{job}")["answers"]
    except Exception as e:  # fail open
        return {"send": True, "error": f"{type(e).__name__}: {e}"}
    p, kind = a["worth_sending"]["noul"], a["kind"]["choice"]
    return {"send": p >= threshold or kind in NEVER_MUTE, "p_send": p, "kind": kind,
            "kind_probs": a["kind"].get("probabilities")}


# ---------------------------------------------------------------- CLI
def _read_state(s):
    if s is None or s == "-":
        s = sys.stdin.read()
    elif s.startswith("@"):
        s = open(os.path.expanduser(s[1:])).read()
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return s


def _parse_opts(spec):
    """'a:desc a|b:desc b' -> {a: desc a, b: desc b}; bare labels allowed."""
    out = {}
    for part in spec.split("|"):
        k, _, v = part.partition(":")
        out[k.strip()] = (v or k).strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jev", description=(__doc__ or "jev").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="ad-hoc questions")
    a.add_argument("--state", "-s", help="text, JSON, @file, or - for stdin (default stdin)")
    a.add_argument("--yes", nargs=2, action="append", metavar=("NAME", "QUESTION"), default=[])
    a.add_argument("--choice", nargs=3, action="append", metavar=("NAME", "QUESTION", "a:desc|b:desc"), default=[])
    a.add_argument("--score", nargs=3, action="append", metavar=("NAME", "QUESTION", "low|mid|high"), default=[])

    r = sub.add_parser("rank", help="rank candidates against a goal")
    r.add_argument("goal")
    r.add_argument("--candidates", "-c", help="JSON list, @file, or - (default stdin). Lines also OK.")
    r.add_argument("--top", type=int, default=10)
    r.add_argument("--context")

    p = sub.add_parser("page", help="classify page state")
    p.add_argument("--text", "-t", help="visible text, @file, or - (default stdin)")
    p.add_argument("--goal")
    p.add_argument("--url")
    p.add_argument("--title")
    p.add_argument("--signals", help="JSON of DOM signals (iframes/inputs/buttons)")

    g = sub.add_parser("gate", help="notification gate; exit 0 send, 10 mute, 2 error(send)")
    g.add_argument("text", nargs="?")
    g.add_argument("--job")
    g.add_argument("--threshold", type=float, default=0.2)

    sub.add_parser("raw", help="full request JSON on stdin")

    o = ap.parse_args(argv)
    try:
        if o.cmd == "ask":
            qs = {n: noul(q) for n, q in o.yes}
            qs.update({n: choice(q, _parse_opts(opts)) for n, q, opts in o.choice})
            qs.update({n: score(q, [x.strip() for x in lv.split("|")]) for n, q, lv in o.score})
            if not qs:
                ap.error("give at least one --yes/--choice/--score")
            res = decide(_read_state(o.state), qs, tag="ask")
            print(json.dumps({"answers": res["answers"], "cost": res.get("usage", {}).get("cost")}, indent=1))
        elif o.cmd == "rank":
            raw = _read_state(o.candidates)
            cands = raw if isinstance(raw, list) else [l for l in str(raw).splitlines() if l.strip()]
            for row in rank(o.goal, cands, context=o.context, top=o.top):
                print(json.dumps(row))
        elif o.cmd == "page":
            t = _read_state(o.text)
            sig = json.loads(o.signals) if o.signals else None
            print(json.dumps(page(t if isinstance(t, str) else json.dumps(t), o.goal, o.url, o.title, sig)))
        elif o.cmd == "gate":
            text = o.text if o.text is not None else sys.stdin.read()
            res = gate(text, o.job, o.threshold)
            print(json.dumps(res))
            sys.exit(2 if "error" in res else (0 if res["send"] else 10))
        elif o.cmd == "raw":
            req = json.load(sys.stdin)
            print(json.dumps(decide(req["state"], req["questions"], req.get("model"), tag="raw"), indent=1))
    except JevError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
