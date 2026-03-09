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
- `make this carplay ready <youtube-url>`

The YNAB skill will prompt for your API token and budget ID on first use. The YouTube skill detects chapters automatically and either splits into an album or produces a single CarPlay-ready MP3.
