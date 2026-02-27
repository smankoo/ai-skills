# ai-skills

Reusable AI agent skills in one repo.

## One-command setup (new machine)

Install everything:

```bash
curl -fsSL https://raw.githubusercontent.com/smankoo/ai-skills/main/bootstrap.sh | bash
```

Install one skill:

```bash
curl -fsSL https://raw.githubusercontent.com/smankoo/ai-skills/main/bootstrap.sh | bash -s -- --skill youtube-carplay-chapter-album
```

## What this repo contains

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
./scripts/install-skill.sh youtube-carplay-chapter-album --target ~/.codex/skills
```

4. Install all skills into Codex:

```bash
./scripts/install-skill.sh --all --target ~/.codex/skills
```

## Bootstrap script options

```bash
./bootstrap.sh --help
```

## Dependencies for `youtube-carplay-chapter-album`

Install on macOS:

```bash
brew install yt-dlp ffmpeg jq
```

## Use in plain language

After installing, ask your agent naturally, e.g.:

- `make this carplay ready <youtube-url>`

The skill should detect chapters automatically and either:
- split into an album when chapters exist, or
- produce a single CarPlay-ready MP3 when there are no chapters.
