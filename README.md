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

- `skills/family-clothing-refresh`
  - Plans a seasonal clothing refresh for a whole family and turns it into a buyable cart
  - Derives children's sizes from measurements and verifies each item is in stock in that exact size
  - Browses real retailer sites (Simons JSON-LD, Gap/Old Navy per-size stock) for live prices
  - Builds consistently formatted HTML "cross-store shopping cart" emails with computed totals
  - Acts as a personal designer: palette, cross-matching pieces, example outfits, priority subset

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

### `family-clothing-refresh`

Python 3.11+ standard library only (`tomllib`, `smtplib`, `imaplib`). Optional, for the full
end-to-end flow: a browser MCP server for live price/stock verification, and SMTP credentials at
`~/.config/owlpost/accounts.toml` for sending.

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
- `make this carplay ready <youtube-url>`

The YNAB skill will prompt for your API token and budget ID on first use. The clothing skill asks
for ages and current measurements, then does the browsing and verification itself. The YouTube
skill detects chapters automatically and either splits into an album or produces a single
CarPlay-ready MP3.
