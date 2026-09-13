---
name: browser-ops
description: Human-grade web browsing from the VPS — bot walls, CAPTCHAs, logins, JS-heavy sites, bookings. Use whenever a browser task needs stealth, credentials, or CAPTCHA solving, or when deciding which machine (VPS vs Angus) should drive the browser.
---

# Browser Ops — human-grade browsing

## Architecture (verified 2026-09-13)

The VPS runs a **dedicated automation Chrome** — real windowed Google Chrome under Xvfb (NOT headless), managed by systemd:

- Service: `systemctl --user status hermes-browser` (user unit, linger enabled, auto-restarts)
- Launcher: `~/.hermes/bin/hermes-browser.sh` — Xvfb 1440x900, CDP on `127.0.0.1:9222`, profile `~/.hermes/chrome-profile`, GL via SwiftShader (`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader` → gives real WebGL fingerprint)
- Hermes wired to it via `browser.cdp_url: http://127.0.0.1:9222` in `~/.hermes/config.yaml` — `browser_exec` uses this Chrome automatically.

**Why this passes bot checks:** windowed real Chrome = clean UA (no HeadlessChrome), `navigator.webdriver` missing, real plugins, WebGL renderer present. Verified passing: bot.sannysoft.com (all green), Cloudflare challenge (nowsecure.nl auto-cleared), simons.ca, costco.ca (both previously blocked from headless).

## Machine routing

| Task | Where |
|---|---|
| Anonymous browsing, scraping, scheduled/cron tasks | VPS (this Chrome) |
| Logged-in flows on Sumeet's accounts (real cookies/sessions) | Angus via open-browser-control MCP (browser_* tools; `browser_request_user` hands control to Sumeet for MFA) |
| IP-reputation-only blocks | VPS + tailscale exit node (see retail-bot-wall-bypass skill) |

## CAPTCHA solving (vision, no paid API — Sumeet's explicit preference)

Proven flow (reCAPTCHA v2 image challenge solved end-to-end 2026-09-13, token issued):

1. Find the widget iframe rect via `js()` (`iframe[title*="reCAPTCHA"]`), click checkbox at `x+27, y+h/2` with `click_at_xy`.
2. If a challenge appears (`iframe[src*="bframe"]` with width>0): `capture_screenshot()` → `vision_analyze(path, "instruction text? grid 3x3 or 4x4? which cells match, numbered left-to-right top-to-bottom?")`.
3. Grid geometry inside bframe: image starts ~(+7, +125) from bframe origin, ~386px wide; cell centers = `origin + col*cell + cell/2`. Click cells with ~1s pauses.
4. Screenshot again → vision-verify selections → click VERIFY (bframe bottom-right, `w-60, h-30`).
5. Success check: `document.querySelector('#g-recaptcha-response').value` non-empty.
6. Retries: re-screenshot each round ("select until none left" variants refresh tiles). Cap at 3 rounds; on failure send the screenshot to Sumeet on Telegram (MEDIA:) and ask him to describe/complete.

For hCaptcha/Turnstile: same pattern — screenshot, vision, click. Cloudflare Turnstile usually auto-passes with this browser; don't click preemptively.

## Credentials (1Password, fetch-at-fill-time)

Never ask Sumeet to paste passwords in chat; never write them to disk or logs.

```bash
export OP_SERVICE_ACCOUNT_TOKEN=$(cat ~/.op_service_token)
op item list --vault "Home Servers"
op item get "<title>" --vault "Home Servers" --fields username,password --reveal
```

Fill via `fill_input(selector, value)` in the same browser_exec call the secret was fetched in; don't print the secret. Site logins Sumeet shares should be saved as 1Password items in Home Servers (op item create), then referenced by title.

## Pitfalls

- **Harness daemon can hang** on CAPTCHA iframes (raw `cdp('Input.dispatchMouseEvent')` timed out & wedged it). Symptoms: every browser_exec call times out. Fix: `pgrep -af browser_harness.daemon` → kill it → rm `~/.config/browser-harness/runtime/bu-default.{pid,sock}` → next browser_exec respawns it. Chrome itself survives.
- Use the harness `click_at_xy` helper, NOT raw Input.dispatchMouseEvent CDP calls.
- After a daemon restart it may bind to the WRONG TAB (not your working one) — often fastest to `goto_url()` and re-run your scripted fills rather than fight tab focus. Keep fills scripted/idempotent so replay is cheap.
- Angular/SPA forms: set values via the native setter (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el, v)`) then dispatch `input` + `change`. Searchable dropdowns (`.list-filter input`, eVisionCare portals): type a prefix, wait, click the matching `li`. Plain `.value=` does NOT register with the framework.
- eVisionCare patient portals (mypatientsportal.com, used by many ON optometrists): new-patient path = Select Location → NEXT → 2-page registration (page 2 optional) → dashboard → Book Appointment → doctor+reason selects → 'Go' is an ANCHOR not button → week calendar with slot anchors → Book Now confirms. Registration alone creates a patient record — only click 'Book Now' when told to actually book.
- systemd + xvfb-run: quoting breaks in ExecStart; that's why the launcher is a bash script.
- Stale `SingletonLock` in the profile prevents Chrome start after crash — launcher rm's it.
- If `browser_exec` says "chrome-not-running": `systemctl --user restart hermes-browser`, wait ~8s, retry.
- Profile persists cookies — good for staying "warm" on sites, but clear `~/.hermes/chrome-profile` if you need a fresh identity.
- This does NOT beat "Press & Hold" interactive challenges reliably — see retail-bot-wall-bypass skill for deep-link workarounds and Mac delegation.

## Verification checklist after any setup change

1. `curl -s http://127.0.0.1:9222/json/version` → Chrome JSON, UA without "Headless".
2. browser_exec → bot.sannysoft.com → WebDriver "missing (passed)", WebGL vendor present.
3. nowsecure.nl → title without "Just a moment".
