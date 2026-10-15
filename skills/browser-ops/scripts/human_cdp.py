#!/usr/bin/env python3
"""Human-like Chrome driver over CDP (for sites with bot detection: Amazon, Costco, banks).

Why sites flag automation, and what this does instead:
  * JS element.click() / dispatchEvent -> isTrusted=false. We ONLY use Input.dispatch* (trusted).
  * Teleporting mouse / zero-time clicks -> we move along a curved path with jitter, hover, then press/release.
  * Instant typing / insertText -> per-key keyDown/char/keyUp with 60-180 ms gaps, occasional pauses.
  * Deep-link jumps to checkout -> navigate like a person: home page, search box, results, product.
  * Datacenter IP + Linux headless UA -> run against the REAL windowed Chrome on the iMac (home IP):
      ssh -fN -L 19334:127.0.0.1:9334 sumeet@100.119.136.41   (profile ~/.hermes/costco-profile)

Library use:
  from human_cdp import Tab
  t = Tab.new("http://127.0.0.1:19334", "https://www.amazon.ca/")
  t.click_sel("#nav-link-accountList"); t.type_sel("#ap_email", "x@y"); t.text()
"""
import json, math, random, time, urllib.request
import websocket


class Tab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self._id = 0
        self.mx, self.my = random.randint(300, 700), random.randint(200, 400)
        self.cdp("Page.enable"); self.cdp("Runtime.enable")

    @classmethod
    def new(cls, endpoint, url="about:blank"):
        t = json.loads(urllib.request.urlopen(urllib.request.Request(
            endpoint + "/json/new?" + urllib.request.quote(url, safe=":/?=&%"), method="PUT")).read())
        tab = cls(t["webSocketDebuggerUrl"]); tab.target_id = t["id"]; tab.endpoint = endpoint
        tab.wait_load(); return tab

    @classmethod
    def attach(cls, endpoint, url_sub):
        for t in json.loads(urllib.request.urlopen(endpoint + "/json").read()):
            if t.get("type") == "page" and url_sub in t.get("url", ""):
                tab = cls(t["webSocketDebuggerUrl"]); tab.target_id = t["id"]; tab.endpoint = endpoint
                return tab
        raise LookupError(url_sub)

    def close(self):
        try: urllib.request.urlopen(self.endpoint + "/json/close/" + self.target_id)
        except Exception: pass

    # ---- plumbing
    def cdp(self, method, **params):
        self._id += 1; i = self._id
        self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == i:
                if "error" in r: raise RuntimeError(f"{method}: {r['error']}")
                return r.get("result", {})

    def js(self, expr):
        r = self.cdp("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def url(self): return self.js("location.href")
    def text(self, n=4000): return (self.js("document.body ? document.body.innerText : ''") or "")[:n]

    def wait_load(self, timeout=30, settle=(1.5, 3.0)):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.js("document.readyState") == "complete": break
            except Exception: pass
            time.sleep(0.4)
        self.pause(*settle)

    @staticmethod
    def pause(a=0.4, b=1.2): time.sleep(random.uniform(a, b))

    # ---- geometry
    def box(self, sel_js):
        """sel_js: JS expression returning an element. Scrolls it into view like a person (wheel)."""
        for _ in range(8):
            r = self.js(f"(() => {{ const e={sel_js}; if(!e) return null; const b=e.getBoundingClientRect(); "
                        f"return [b.x,b.y,b.width,b.height, innerHeight]; }})()")
            if not r: return None
            x, y, w, h, vh = r
            if 60 < y < vh - 80: return x, y, w, h
            self.wheel(int((y - vh / 2) * random.uniform(0.8, 1.0)))
        return x, y, w, h

    def wheel(self, dy):
        steps = max(2, abs(dy) // 120)
        for _ in range(int(steps)):
            self.cdp("Input.dispatchMouseEvent", type="mouseWheel", x=self.mx, y=self.my, deltaX=0,
                     deltaY=dy / steps + random.uniform(-8, 8))
            time.sleep(random.uniform(0.03, 0.09))
        self.pause(0.3, 0.8)

    def move(self, x, y):
        sx, sy = self.mx, self.my
        cx, cy = (sx + x) / 2 + random.uniform(-80, 80), (sy + y) / 2 + random.uniform(-60, 60)
        n = random.randint(14, 28)
        for i in range(1, n + 1):
            t = i / n; t = t * t * (3 - 2 * t)  # ease in/out
            px = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * x + random.uniform(-1.2, 1.2)
            py = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * y + random.uniform(-1.2, 1.2)
            self.cdp("Input.dispatchMouseEvent", type="mouseMoved", x=px, y=py)
            time.sleep(random.uniform(0.006, 0.022))
        self.mx, self.my = x, y

    def click_xy(self, x, y):
        self.move(x, y); self.pause(0.08, 0.35)
        self.cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        time.sleep(random.uniform(0.05, 0.14))
        self.cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

    def click(self, sel_js):
        b = self.box(sel_js)
        if not b: raise LookupError(sel_js)
        x, y, w, h = b
        self.click_xy(x + w * random.uniform(0.3, 0.7), y + h * random.uniform(0.35, 0.65))
        self.pause(0.5, 1.3)

    def click_sel(self, css): self.click(f"document.querySelector({json.dumps(css)})")

    def click_text(self, regex, scope="button,a,input[type=submit],span.a-button-inner,[role=button],label,li"):
        self.click(f"[...document.querySelectorAll({json.dumps(scope)})].find(e=>e.offsetParent && "
                   f"new RegExp({json.dumps(regex)},'i').test((e.innerText||e.value||'').trim()))")

    # ---- keyboard
    def key(self, key, code=None, vk=None, text=None):
        p = {"key": key, "code": code or key, "windowsVirtualKeyCode": vk or 0}
        self.cdp("Input.dispatchKeyEvent", type="keyDown", **p, **({"text": text} if text else {}))
        self.cdp("Input.dispatchKeyEvent", type="keyUp", **p)

    def type(self, s, wpm_fast=False):
        # Key events don't reach a background Chrome window on the Mac (verified 2026-10-14:
        # keyDown/char and Backspace were ignored), but Input.insertText produces trusted
        # beforeinput/input events. So type one character at a time with human timing.
        for ch in s:
            self.cdp("Input.insertText", text=ch)
            time.sleep(random.uniform(0.04, 0.11) if wpm_fast else random.uniform(0.06, 0.18))
            if random.random() < 0.04: time.sleep(random.uniform(0.25, 0.6))

    def type_sel(self, css, s, clear=True):
        self.click_sel(css)
        if clear:
            self.js(f"(() => {{ const e=document.querySelector({json.dumps(css)}); e.select && e.select(); }})()")
            if self.js(f"document.querySelector({json.dumps(css)}).value.length"):
                self.cdp("Input.insertText", text="")  # replaces the selection
                self.js(f"(() => {{ const e=document.querySelector({json.dumps(css)}); if(e.value) {{ e.select(); document.execCommand('delete'); }} }})()")
        self.type(s)

    def enter(self): self.key("Enter", code="Enter", vk=13, text="\r")

    def navigate(self, url):
        """Use sparingly (a person types/clicks). Fine for the home page."""
        self.cdp("Page.navigate", url=url); self.wait_load()


if __name__ == "__main__":
    import sys
    t = Tab.new(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "about:blank")
    print(t.url()); print(t.text(800))
