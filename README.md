# ai-skills
[![CI](https://github.com/smankoo/ai-skills/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/smankoo/ai-skills/actions/workflows/ci.yml)

Reusable AI agent skills in one repo.

## One-command setup (new machine)

Install everything:

```bash
curl -fsSL https://raw.githubusercontent.com/smankoo/ai-skills/main/bootstrap.sh | bash
```

Install everything for both Codex and Claude:

```bash
curl -fsSL https://raw.githubusercontent.com/smankoo/ai-skills/main/bootstrap.sh | bash -s -- --agent both
```

Install one skill:

```bash
curl -fsSL https://raw.githubusercontent.com/smankoo/ai-skills/main/bootstrap.sh | bash -s -- --skill ynab
```

## What this repo contains

- `skills/ynab`
  - Full YNAB (You Need A Budget) integration via the YNAB API
  - Python CLI client with 25+ commands for accounts, transactions, categories, payees, and more
  - Analysis tools: spending breakdown, recurring expense detection, income vs expenses, category trends, subscription detection, budget health check
  - Automatic milliunit conversion, rate limiting, and fuzzy name resolution
  - Complete API reference documentation

- `skills/personal-shopper`
  - Acts as a personal shopper: wardrobes, occasion outfits with a hard date, and gift shopping
  - Derives children's sizes from measurements and verifies each item is in stock in that exact size
  - Browses real retailer sites for live prices and per-size stock (JSON-LD, per-size availability)
  - For gifts, finds several genuinely distinct directions, costs each, and recommends one
  - Checks delivery dates against the deadline, not just stock — and flags what can't arrive in time
  - Builds consistently formatted HTML shopping-cart emails with item thumbnails and computed totals
  - Carries **no personal data**: names, sizes, budgets, stores, and addresses come from your own
    records (via an MCP, if you have one) or from asking — nothing is baked into the skill
  - **Self-improving**: each run writes what it learned about a retailer's site — selectors, URL
    shapes, failure modes — back into its own reference files, so the next run doesn't relearn it

- `skills/youtube-carplay-chapter-album`
  - Converts a chaptered YouTube URL into CarPlay-ready MP3 album tracks
  - Adds per-track metadata and embedded artwork

- `skills/ynab-reconcile`
  - Reconciles YNAB accounts against downloaded bank data (OFX/CSV/screenshots)
  - Matches bank and YNAB transactions by amount (dates only disambiguate), across
    statement-window and pending-transaction edge cases
  - Reports bank-not-in-YNAB adds, YNAB-not-on-bank items to classify, and amount
    mismatches to edit -- and shows proposed changes before writing anything
  - Leaves the final residual to an in-app YNAB Reconcile rather than faking an
    adjustment via the API
  - Carries **no account list or credentials**: token and budget ID come from the
    environment at run time

- `skills/send-to-kindle`
  - Sends an epub/pdf/document to a Kindle end-to-end via Amazon's Send to Kindle
    email feature
  - Handles the non-obvious part: Amazon's verification email is required on every
    send and often lands in a different mailbox than the one that sent the document
  - Confirms the document by fetching the verification link directly (no browser or
    login needed)
  - Carries **no email addresses**: send-from, send-to, and verification-inbox
    addresses are asked for and used only for the run

- `skills/book-car-service`
  - Books a service appointment through a dealership's online scheduler
  - Knows to drive a Keyloop "SWA" (or similar) booking widget's own URL directly when
    the dealer's marketing page only embeds it in a cross-origin iframe
  - Works out which maintenance package is due from the odometer and the dealer's own
    package list, rather than guessing
  - Carries **no vehicle, dealer, or personal details**: all of it comes from the user
    or their own connected records

## Install a skill

1. Clone the repo:

```bash
git clone https://github.com/smankoo/ai-skills.git
cd ai-skills
```

2. List available skills:

```bash
./scripts/install-skill.sh --list
```

3. Install one skill into Codex:

```bash
./scripts/install-skill.sh ynab --agent codex
```

4. Install one skill into Claude Code:

```bash
./scripts/install-skill.sh ynab --agent claude
```

5. Install all skills into both:

```bash
./scripts/install-skill.sh --all --agent both
```

## Bootstrap script options

```bash
./bootstrap.sh --help
```

## Dependencies

### `ynab`

No external dependencies — uses only Python standard library (`urllib`, `json`).

### `personal-shopper`

Python 3.11+ standard library only (`tomllib`, `smtplib`, `imaplib`). Optional, for the full
end-to-end flow:

- A browser MCP server, for live price and per-size stock verification.
- SMTP credentials in a TOML file, for sending. Defaults to `~/.config/owlpost/accounts.toml`;
  override with `--config` or `$SHOPPER_ACCOUNTS_FILE`. See the header of
  `skills/personal-shopper/scripts/send_email.py` for the expected shape.
- A personal-records MCP (the skill knows Pebbleway's tool names), so it can look up people and
  measurements instead of asking. Entirely optional — without one it just asks you.

### `youtube-carplay-chapter-album`

Install on macOS:

```bash
brew install yt-dlp ffmpeg jq
```

### `ynab-reconcile`

Python 3 standard library only (`urllib`, `json`, `csv`, `re`, `argparse`). Needs a
YNAB Personal Access Token and budget ID, set as `YNAB_TOKEN` and `YNAB_BUDGET` in the
environment. Reconciling also needs a downloaded bank export (OFX or CSV) to compare
against.

### `send-to-kindle`

No bundled scripts -- needs a mail-sending tool that can send with attachments and read
another mailbox (an MCP mail server, or your own `smtplib`/IMAP setup), plus the
user's Kindle email address (from Amazon's Personal Document Settings) approved to
receive documents.

### `book-car-service`

Needs a browser-automation tool that can navigate and interact with a live web page.
No API keys; everything else (vehicle, dealer, calendar) is supplied by the user or
their own connected records at run time.

## Use in plain language

After installing, ask your agent naturally, e.g.:

- `what's my net worth?`
- `show my spending by category for the last 3 months`
- `detect my subscriptions`
- `the kids need clothes for the fall`
- `my son starts daycare in three weeks, sort out what he needs`
- `my nephew's graduation is on the 21st, he needs something nice`
- `my brother-in-law's 40th is Sunday and we need a gift — find a few different directions`
- `make this carplay ready <youtube-url>`

The YNAB skill will prompt for your API token and budget ID on first use. The personal-shopper
skill asks for ages and current measurements (or, for a gift, the budget band and anything you know
about the recipient), then does the browsing and verification itself. The YouTube skill detects
chapters automatically and either splits into an album or produces a single CarPlay-ready MP3.

## A note on personal data

These skills hold **method, not personal data**. No names, sizes, addresses, budgets, or credentials
are committed anywhere — each skill either reads what it needs from your own systems at runtime or
asks you. That's deliberate, so a skill can be shared or published without leaking whoever wrote it.
Worked examples in the references are anonymised and illustrative; treat any number in them as a
placeholder, not a default. If you extend a skill, keep it that way: write the *lesson* into the
skill and leave the specifics in your run's output.
