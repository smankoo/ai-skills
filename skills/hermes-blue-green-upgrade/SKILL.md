---
name: hermes-blue-green-upgrade
description: >
  Safely upgrade this self-hosted Hermes gateway to a new release using a
  zero-risk blue/green deployment with an offline acceptance-test gate and
  automatic rollback. Use when the user wants to update/upgrade Hermes,
  bump to a new version/tag, or retry an upgrade that was previously deferred.
  The agent runs INSIDE the gateway it is upgrading, so the cutover/rollback
  must be driven by an EXTERNAL systemd oneshot — never from a tool call.
---

# Hermes blue/green self-upgrade (zero-risk, test-gated)

Upgrade the running Hermes gateway to a new release with **no irreversible
step**: build the new version alongside the old, prove it with an offline
acceptance suite, flip an atomic symlink, health-gate, and auto-rollback if
anything is wrong. The old version is never mutated, so rollback is instant.

## When to use
- User says "upgrade Hermes", "update to vX", "retry the upgrade", "cut over".
- A previously-deferred upgrade's scheduled window arrives.

## Core principles (learned the hard way — 2026-08-13, the v0.20.0 attempt)
1. **Keep the core vanilla.** All customization lives in `HERMES_HOME`
   (`~/.hermes/`): config, plugins, skills, crons, memory. The code
   tree is disposable. A new version is a fresh clone, not a patched tree. This
   is why blue/green is cheap — green shares the SAME `HERMES_HOME` state.
2. **The agent cannot rescue its own runtime.** A tool call that restarts the
   gateway is killed by the gateway's own SIGTERM. So cutover AND rollback run
   as **external systemd oneshots** (`systemctl --user start --no-block …`),
   each in its own cgroup. Never `systemctl restart hermes-gateway` from a
   terminal tool — the lifecycle guard blocks it anyway.
3. **Telegram allows ONE poller per bot token.** Blue and green cannot both
   hold `getUpdates`. So this is **atomic-cutover** blue/green (stage green
   offline, validate, flip in one step), NOT simultaneous dual-serving.
4. **"It imports and `doctor` is clean" is NOT enough.** v0.20.0 passed a naive
   smoke test yet shipped a bug that crashed every absolute-path command the
   agent runs. The acceptance suite must exercise the REAL code paths that can
   break, and assert behavior (no crash AND safety preserved), not just import.
5. **Reproduce bugs by observation, not theory.** When a probe won't reproduce
   a known live crash, trace the actual call path (args, callbacks, sizes)
   instead of guessing. The v0.20.0 crash only fired when the guard's
   `read_remote_script` callback fed a binary's decoded bytes back into the
   recursion — omitting that callback (or capping the read) hid the bug.

## Layout (already built; reuse in place)
```
~/.hermes/
  hermes-agent/                 # BLUE = current live install (leave untouched)
  releases/<tag>/               # GREEN = fresh clone at <tag> + own venv
  hermes-current -> {blue|green}# SYMLINK the gateway unit's ExecStart uses
  bluegreen/
    hermes-bluegreen.sh         # orchestrator: status|stage|smoke|test|cutover|rollback
    build_green.sh              # clone <tag> + build venv
    upgrade_acceptance.py       # the offline test gate (pass=safe, fail=block)
    required_runtime.conf       # EXTRAS/PINS/IMPORTS every release's REAL runtime must carry
    runtime-<tag>               # generated: python shim over <tag>'s pm env (what the gate runs)
    unit.<tag>                  # gateway unit snapshot per release, restored on rollback
    last_good                   # rollback target (path to the known-good release)
    orchestrator.log            # audit trail of every flip
~/.config/systemd/user/
  hermes-gateway.service        # ExecStart -> …/hermes-current/venv/bin/python …
  hermes-upgrade@.service       # oneshot: ExecStart=hermes-bluegreen.sh cutover %i
  hermes-rollback.service       # oneshot: ExecStart=hermes-bluegreen.sh rollback
```

## Procedure

### 0. Preflight (verify the safety net BEFORE relying on it)
- Confirm gateway is healthy and note its PID:
  `systemctl --user show hermes-gateway -p MainPID -p ActiveState`
- Confirm the health-gate markers still exist in the TARGET version's
  `gateway/run.py` (`Gateway running with` and `connected`). If the wording
  changed, update `health_check()` in the orchestrator or the gate never passes.
- Test the Telegram notify channel end-to-end (the orchestrator's `notify()`)
  and ask the user to confirm they received the test ping. A silent rollback
  while the user is AFK is the one failure we cannot tolerate.
- Set `XDG_RUNTIME_DIR=/run/user/$(id -u)` for all `systemctl --user` calls.

### 1. Stage green (safe, offline, does not touch the live gateway)
`bluegreen/hermes-bluegreen.sh stage <tag>`  → full clone at `<tag>` + venv.
Use a **full** clone at the exact tag (not shallow) so there's no phantom
"+N carried commits" version string.

### 2. Point the gateway unit at the symlink (one-time, inert)
Rewrite `hermes-gateway.service` so ExecStart/PATH/VIRTUAL_ENV/ExecStopPost all
use `…/hermes-current/…` instead of a hardcoded release dir, then
`systemctl --user daemon-reload`. This is INERT: it doesn't restart the
gateway, and while `hermes-current -> blue` the resolved command is byte
identical. Verify same PID afterward.

### 3. Gate: run the acceptance suite offline against green
`bluegreen/hermes-bluegreen.sh test <tag>`
- Exit 0 → green is safe; proceed.
- Exit 1 → green is broken; **DO NOT cut over.** Report the failing probe,
  keep serving on blue, and (optionally) root-cause + file/patch upstream.
The `cutover` command runs this same gate automatically and refuses to flip if
it fails — but running `test` first gives a clean go/no-go before committing.

### 4. Cut over (external oneshot; first run should be ATTENDED)
`systemctl --user start --no-block hermes-upgrade@<tag>.service`
The oneshot: runs the acceptance gate → snapshots the unit → flips symlink→green
→ restarts gateway → health-gates ~120s → **canary**: one real model call through
green (`-z "What is 17 + 25?"`, must contain 42, 3 tries 30s apart) → on success
rewrites the PATH shim and pings "upgrade complete"; on any failure restores the
previous unit + symlink, auto-rolls-back and pings "rolled back, you're safe".
The gateway blips ~15-30s; the agent's session is restored afterward. After the
restart, VERIFY where you landed (read-only): `readlink hermes-current`,
`… version`, and `tail bluegreen/orchestrator.log`. Do NOT re-run the restart.

### 5. Roll back (any time, instant)
Force back to blue: point `last_good` at blue then fire the oneshot:
```
echo "$HOME/.hermes/hermes-agent" > bluegreen/last_good
systemctl --user start --no-block hermes-rollback.service
```
GOTCHA: a successful cutover overwrites `last_good` with green. Before a
deliberate rollback, re-point `last_good` at blue or `rollback` will no-op.

## Pitfalls (all hit for real on 2026-08-13)
- **v0.22+ does not run `<release>/venv`. The gate used to test the wrong interpreter (2026-10-16).**
  The gateway starts through `<release>/.hermes/bin/hermes`, a launcher that runs a **pm-managed env**
  under `~/.hermes/installs/<id>/environments/<env>/venv`. That env is keyed to the checkout dir, so a
  fresh green gets pm's defaults (`anthropic, telegram`) no matter what blue had. v0.22.2 passed the old
  gate 10/10, because the gate tested `./venv`, while the live runtime had no `boto3`, `mcp`,
  `faster_whisper` or `ollama`. **Every** Bedrock call (chat and cron) then died with
  "No module named 'botocore'", and the gateway still looked healthy. Now:
  - `bluegreen/required_runtime.conf` is the floor: EXTRAS (installed via `pm install --extra`), PINS
    (uv-installed into the pm env, e.g. `ollama`), IMPORTS (checked only, e.g. `aiohttp`, because pm's anchor for
    `messaging` is `telegram`). `build_green.sh` installs the floor plus every extra the LIVE release
    carries (`hermes-current/.hermes/bin/hermes pm status` → `feature_list`).
  - `upgrade_acceptance.py` resolves the real env (`<release>/.hermes/bin/hermes --run-module site`) and
    runs every probe through `bluegreen/runtime-<tag>`, a shim over that env's python. `runtime_deps`
    imports every required module there.
  - Inspect a live release's real env: `<release>/.hermes/bin/hermes --run-module site`, and
    `… pm status`. Adding an extra by hand: `<release>/.hermes/bin/hermes pm install --extra X` (and
    add it to required_runtime.conf so the next green carries it).
- **Isolated plugin venvs inherit the host's Python env (2026-10-16).** crawl4ai's 3.11 venv imported 3.14
  C-extensions through an inherited `PYTHONPATH` and failed every extract (silently rescued by keyless Exa).
  The fix is in the plugin (clean `env=`); see hermes-web-search-backends `references/crawl4ai-extract-backend.md`.
  After cutover: `grep "crawl4ai' failed" ~/.hermes/logs/agent.log`.
- **v0.22+ rewrites its own gateway unit (2026-10-16).** After its first start it hardcodes
  `…/releases/<tag>/.hermes/bin/hermes` into `hermes-gateway.service`, bypassing `hermes-current`. A
  symlink-only rollback then restarts the SAME release and reports healthy. Cutover now snapshots the
  unit as `bluegreen/unit.<prev-tag>`, and every rollback restores it + `daemon-reload`.
  (`unit.v2026.8.27` was reconstructed from `hermes-gateway.service.blue-backup` with paths pointing at
  hermes-current.)
- **A stale CLI on PATH drains the gateway (2026-10-16).** Running an older release's `hermes` SIGTERMs
  the newer gateway ~30s later ("Gateway draining: service_draining"). `~/.local/bin/hermes` is now a
  shim that always execs `hermes-current`'s CLI; cutover/rollback rewrite it.
- **The dashboard follows `hermes-current` too (2026-10-16).** `hermes-dashboard.service` runs
  `hermes-current/.hermes/bin/hermes dashboard … --skip-build` (template in `~/p/vps`
  roles/hermes, authoritative). It serves `hermes_cli/web_dist`, which is not in git, so
  `build_green.sh` now runs a full `npm install --include=dev` + `npm run build -w web` (the old
  `--omit=dev` meant tsc failed on vitest types and no green ever had a UI). The `dashboard_dist`
  probe blocks cutover without it. Cutover and rollback restart the dashboard. Each cutover also
  snapshots the dashboard unit as `dashboard.<prev-tag>`. **`dashboard.v2026.8.27` serves from
  `~/.hermes/hermes-agent`** (v2026.8.27 has no built UI), so `hermes-agent` is NOT an orphan
  while v2026.8.27 is the rollback target. Don't prune it until a newer release becomes `last_good`.
- **Ansible's `hermes-autoupdate.timer` is OFF (2026-10-16).** It upgraded `~/.hermes/hermes-agent`
  in place daily and restarted the gateway. Two upgraders for one gateway. Disabled live and in
  `~/p/vps` (`hermes_autoupdate_enabled: false`, `hermes` removed from memwatch's components). Do not
  re-enable it; upgrades go through this skill.
- **Probes track refactors.** v0.21+ split `gateway/run.py` into `run_*.py` (the health marker
  "Gateway running with" now lives in `run_startup.py`) and moved MCP helpers into
  `tools/mcp_tool_config.py` and `tools/mcp_tool_discovery.py`. Both probes now handle old and new
  layouts. Before blaming a release, validate a failing probe against blue.
- **Disk:** each release is about 2.6 GB. Check `df` before staging; at 94% (2026-10-16), prune orphans
  first.
- **Green venv MUST include the `[mcp]` extra** (2026-10-13). `pip install -e .`
  alone omits the `mcp` SDK; `discover_mcp_tools()` then logs only a DEBUG
  "MCP SDK not available" and returns [] -> every chat silently loses ALL MCP
  tools (pebbleway, nutrition, agora, whatsapp) while the servers look healthy.
  `build_green.sh` now installs `.[mcp]`; acceptance probe `mcp_discovery`
  fails the gate if configured servers yield 0 tools. Quick check on a live
  release: `<release>/venv/bin/python -c "import mcp"`.
- **Self-restart is blocked.** `hermes-bluegreen.sh rollback` invoked directly
  in a terminal tool is refused (contains a gateway-lifecycle command). Always
  go through the systemd oneshot.
- **`last_good` drift.** See step 5 gotcha.
- **Health regex staleness.** If the target renames log lines, the gate can't
  pass → false rollback. Check step 0.
- **Nested-quote `tr` in bash.** Strip quotes from `.env` values with `sed`,
  not a `tr '"'"'"'…` monster (it broke the script once).
- **Reading a secret can hardline-block a command.** Don't `grep`/echo the bot
  token yourself; let the orchestrator read it internally at runtime.
- **cryptography pin vs crawl4ai.** Hermes pins cryptography <49 (msal/alibaba
  caps); crawl4ai needs >=49. It stays in its own isolated venv
  (`~/.hermes/crawl4ai-venv`, cryptography 50) and the plugin shells out to it —
  this is unchanged by any upgrade. Don't try to retire the isolated venv.

## Disk hygiene — prune orphaned release trees (do this after every cutover)
Each staged release is a **full ~2 GB code tree + venv**. They live forever
under `~/.hermes/releases/<tag>/` (plus the original `hermes-agent/` blue tree)
unless pruned, so after a few upgrades `~/.hermes` balloons — three 2 GB copies
was the top disk hog on the VPS (found 2026-08-28: `releases/` + `hermes-agent`
were ~6.4 GB of an 8.1 GB `.hermes`). Only **two** trees are ever needed:
- **LIVE** — whatever `readlink ~/.hermes/hermes-current` resolves to.
- **ROLLBACK** — the path in `~/.hermes/bluegreen/last_good`.

Everything else in `releases/` (and `hermes-agent` itself once it is neither
live nor the rollback target) is an orphan and is safe to `rm -rf`. Safe prune:
```
LIVE=$(readlink -f ~/.hermes/hermes-current)
ROLLBACK=$(readlink -f "$(cat ~/.hermes/bluegreen/last_good)")
for d in ~/.hermes/releases/*/ ~/.hermes/hermes-agent; do
  p=$(readlink -f "$d")
  [ "$p" = "$LIVE" ] || [ "$p" = "$ROLLBACK" ] || echo "ORPHAN: $d"
done
```
Verify the two anchors print correctly, eyeball the ORPHAN list, then delete
those dirs. **Never** delete the live or rollback tree. Note: after a
successful cutover `last_good` points at green (the new live), so the OLD blue
becomes the rollback and the pre-previous release is the orphan to reap — i.e.
keep the current + one-back, drop everything older. Fold this prune into the
end of the cutover flow (step 4) so it self-cleans and never accumulates again.

## Extending the acceptance suite
`upgrade_acceptance.py` is additive: **every regression we ever eat gets a new
probe**, so we never eat it twice. Each probe returns (name, passed, detail);
non-zero overall exit blocks cutover. Probes run against ANY release dir via
`<release>/venv/bin/python … <release_dir>`. Invoke with a PATH-resolved
`python3` + relative path so the invocation itself can't trip the guard bug it
is testing. Validate a new probe by confirming it PASSES on blue (known-good)
and FAILS on the release that exhibited the bug.
