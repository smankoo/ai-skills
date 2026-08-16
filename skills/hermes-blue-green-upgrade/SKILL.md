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
The oneshot: runs the acceptance gate → flips symlink→green → restarts gateway
→ health-gates ~120s → on success pings "upgrade complete"; on failure
auto-rolls-back to blue and pings "rolled back, you're safe".
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

## Extending the acceptance suite
`upgrade_acceptance.py` is additive: **every regression we ever eat gets a new
probe**, so we never eat it twice. Each probe returns (name, passed, detail);
non-zero overall exit blocks cutover. Probes run against ANY release dir via
`<release>/venv/bin/python … <release_dir>`. Invoke with a PATH-resolved
`python3` + relative path so the invocation itself can't trip the guard bug it
is testing. Validate a new probe by confirming it PASSES on blue (known-good)
and FAILS on the release that exhibited the bug.
