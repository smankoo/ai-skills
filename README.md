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
