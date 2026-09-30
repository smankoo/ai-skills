---
name: jev
description: "Use when an agent or automation needs a fast, cheap, calibrated DECISION rather than prose — classify, route, gate, rank, or yes/no-check text. Wraps TypeSafe Jev (typesafe/jev-1.13, OpenRouter Decisions API): ~0.2s, ~$0.00003/call, typed answers with probabilities. Covers browsing (rank links, detect captcha/login/bot walls, 'is the answer on this page?'), cron notification gating, email/transaction triage, and search-result filtering."
version: 1.0.0
metadata:
  hermes:
    tags: [jev, typesafe, openrouter, classification, routing, decisions, browsing, cron, triage]
    related_skills: [browser-ops, cron-job-hygiene, ynab, email-correspondence]
---

# Jev — fast typed decisions

Jev is a **System One** decision model from TypeSafe, served on OpenRouter. It is **not a chat
model**: it writes no text. You give it a `state` (text or JSON) plus questions you define, and it
returns typed answers with calibrated probabilities in about 0.2 seconds.

| Primitive | Asks | Returns |
|---|---|---|
| `noul` | yes / no | `noul`: P(yes) 0-1 |
| `choice` | one of N labelled options | `choice`, `probabilities`, `confidence` |
| `score` | position on an ordered scale | `score` (weighted), `probabilities`, `confidence` |

All questions in one request see the same state and are answered **in parallel and
independently**, so batch them: 50 questions cost about the same wall time as 1.

**Price / limits (Jev 1.13, verified 2026-09-29):** $0.042 per M input tokens, output is free.
State budget is 32k tokens (state plus the longest question); 64k for state plus all questions.
The provider documents 40 req/s. Input is text only, and English gives the best accuracy.

## Setup

1. OpenRouter key: `$OPENROUTER_API_KEY`, or a 0600 file at `~/.config/jev/openrouter_key`.
   On Sumeet's nodes the key is the 1Password (Home Servers vault) item
   **"OpenRouter API Key - laptop"**. No TypeSafe account is needed.
2. CLI: `ln -sf ~/.ai-skills/skills/jev/scripts/jev.py ~/.local/bin/jev`
3. Library (inside `browser_exec`, `execute_code`, or cron scripts):
   ```python
   import sys, os; sys.path.insert(0, os.path.expanduser("~/.ai-skills/skills/jev/scripts")); import jev
   ```

## API (the endpoint is NOT chat/completions)

`POST https://openrouter.ai/api/alpha/decisions`
```json
{"model": "typesafe/jev-1.13",
 "state": {"ticket": "Checkout page is blank after clicking Pay"},
 "questions": {
   "is_bug": {"type": "noul", "instructions": "Is this a software defect?",
              "criteria": {"true": "Broken behaviour", "false": "Question or feature request"}},
   "team":   {"type": "choice", "instructions": "Which team owns it?",
              "criteria": {"payments": "Checkout/billing", "frontend": "Rendering/browser"}},
   "urgency":{"type": "score", "instructions": "How urgent?",
              "criteria": ["Next release", "This week", "Blocking revenue now"]}}}
```
`instructions` and criteria values may be **JSON objects** (e.g. `{"question": ..., "candidate":
"candidates.c3"}`) to point a question at one field of the state. `rank()` relies on this.

## CLI cheatsheet

```bash
# ad-hoc
echo "<email text>" | jev ask --yes promo "Is this marketing?" \
    --choice cat "Category" "bill:bills|service:appointments|promo:marketing|personal:family" \
    --score urg "Urgency" "ignore|this month|this week|today"

# rank candidates (JSON list, or one per line) against a goal, in one call
jev rank "Book a service appointment" -c @links.json --top 5

# page state (+ does it already answer the goal?)
jev page --goal "renew passport" --url "$URL" --title "$T" --signals "$SIG_JSON" < page.txt

# cron notification gate: exit 0 send, 10 mute, 2 error (fail OPEN)
jev gate --job "Daily VPS Health Check" < draft.txt

# full custom request
jev raw < request.json
```

## Browsing with Jev (inside browser_exec)

```python
import sys, os; sys.path.insert(0, os.path.expanduser("~/.ai-skills/skills/jev/scripts")); import jev
st   = jev.page_from(js, goal)          # {"kind", "kind_conf", "kind_probs", "has_answer"}
best = jev.links_from(js, goal, top=5)  # [{"p", "candidate": {"text", "href", "tag", "i"}}]
```
- `kind` is one of `content | login_wall | captcha | bot_block | cookie_or_modal | error | paywall`.
  Use it to branch: captcha or bot_block → browser-ops recovery ladder; login_wall → credentials
  flow or ask the user; cookie_or_modal → dismiss, then re-check.
- `has_answer >= 0.8` → stop navigating and extract. Below 0.5 → keep going.
- `links_from` scores up to 200 visible links and buttons in ONE call. Use it to pick the next click
  instead of reading the whole page with the big model.

**Verified on live sites (2026-09-29):**
- canada.ca "renew passport" put "Get a passport" first (p 0.90).
- ontario.ca → "Renew a health card" (p 0.96) → arrived, has_answer 0.94, in **one hop**.
- Canadian Tire 404 → `error` (conf 1.0). accounts.google.com → `login_wall` (0.98).

### What Jev does NOT replace in browsing
It decides; it does not read pixels, fill forms, or plan multi-step flows. Keep the big model (or
the user) for anything that commits money, submits personal data, or is irreversible. Jev can
only nominate the candidate for those steps; the final "do it" decision stays with the big model or the user.

## Other proven / intended uses

- **Cron notification gate.** Live on the Daily VPS Health Check via `~/.hermes/scripts/jev_gate.py`,
  a wrapper over `jev.gate`. Tuned on 60 real cron reports: routine all-clears score p 0.05-0.09,
  real signal scores ≥ 0.37, so the **threshold is 0.2**. The `failure`, `needs_action` and `security`
  kinds are **never muted**, whatever p says. The job prompt pipes its draft to the gate and
  replies `[SILENT]` on exit 10. Log: `~/.hermes/cron/jev_gate.log`.
- **Search-result / candidate filtering.** Run `rank` over web_search hits before spending
  web_extract calls on them.
- **Email triage.** One call returns needs_action, category and urgency (overdue-bill test: 0.85 /
  bill 1.0 / "this week" 0.91).
- **Transaction categorisation (YNAB).** Use a `choice` over the budget's category names, with the
  payee, memo and amount as state. Auto-apply only when `confidence ≥ 0.9`; otherwise leave the
  transaction for review.
- **Tool-call / action gating.** Ask noul "is this command destructive or irreversible?" before an
  autonomous agent runs it (TypeSafe cookbook: *Gate Agent Tool Calls with Jev*).
- **Verify a cheap model's answer.** Ask noul "does the answer satisfy the question and the evidence?";
  escalate to a big model only when it says no (cookbook: *Jev-Verified Cascade*).

## Confidence and thresholds

- Noul returns only `noul` (P(yes)), with no `confidence`. Choice and Score return `confidence`.
- Scale thresholds to the stakes. Below 0.5 confidence → don't act (ask, or fall back to the big
  model). Read-only actions can go ahead at a medium level. Destructive actions need ≥ 0.9 AND a
  second check.
- **Tune on real data before trusting a threshold.** Replay 30-60 historical items, print p per
  item, and look for the gap. The gate's 0.2 came from exactly this, and the first pass caught a
  real miss (below).

## Pitfalls (all hit for real)

1. **It is hidden from `/api/v1/models`,** and `chat/completions` rejects it with "is a decisions
   model". Don't conclude "not available". `typesafe/jev-router` is a *different* product, a chat
   router that forwards to GPT or DeepSeek, and it does not return decisions.
2. **A missing category means a silent wrong answer.** The first gate had no `security` kind, so a 🚨
   AIDE filesystem-integrity alert scored as routine and would have been muted. Give every choice
   a bucket for each thing that must never be mis-filed, and hard-code a never-mute or never-act list in code.
3. **CAPTCHAs live in iframes, not in innerText.** On the reCAPTCHA demo, text-only input gave a
   51/49 split. Always pass `SIGNALS_JS` (iframe srcs, inputs, buttons); `page_from` does this.
4. **Near-empty pages are ambiguous.** A Cloudflare pass page whose text is only a title
   classified as content at 0.47 confidence. Treat `kind_conf < 0.6` as "look properly", not as an answer.
5. **Fail open where silence is dangerous** (gates, alerts), and **fail closed where action is
   dangerous** (auto-approve, auto-categorise). `jev.gate` already fails open.
6. **Pin `typesafe/jev-1.13`** for anything with tuned thresholds. `~typesafe/jev-latest` moves on
   release and your thresholds silently shift. Override with the `JEV_MODEL` env var for experiments.
7. **The state cap is 32k tokens.** `decide()` truncates string state at about 90k chars. For long pages,
   pass the relevant slice (main/article text), not the whole DOM.

## Observability

Every call is appended to `~/.cache/jev/calls.jsonl` with the timestamp, tag, latency, model, cost
and answers (no state text). For a quick spend check:
`python3 -c "import json;print(sum(json.loads(l).get('cost') or 0 for l in open('$HOME/.cache/jev/calls.jsonl')))"`
