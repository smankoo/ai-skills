#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Bootstrap ai-skills on a new machine.

Usage:
  bootstrap.sh [--all] [--skill NAME[,NAME...]] [--target DIR] [--repo-dir DIR] [--skip-deps]

Options:
  --all                 Install all skills (default behavior)
  --skill LIST          Install specific skills (comma-separated)
  --target DIR          Destination skills directory (default: ~/.codex/skills)
  --repo-dir DIR        Local checkout dir (default: ~/.ai-skills)
  --skip-deps           Skip dependency installation
  -h, --help            Show help

Examples:
  bootstrap.sh --all
  bootstrap.sh --skill youtube-carplay-chapter-album
  bootstrap.sh --skill youtube-carplay-chapter-album --target ~/.codex/skills
USAGE
}

TARGET_DIR="$HOME/.codex/skills"
REPO_DIR="$HOME/.ai-skills"
SKIP_DEPS=0
INSTALL_ALL=1
SKILL_LIST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      INSTALL_ALL=1
      shift
      ;;
    --skill)
      [[ $# -ge 2 ]] || { echo "Missing value for --skill" >&2; exit 1; }
      INSTALL_ALL=0
      SKILL_LIST="$2"
      shift 2
      ;;
    --target)
      [[ $# -ge 2 ]] || { echo "Missing value for --target" >&2; exit 1; }
      TARGET_DIR="$2"
      shift 2
      ;;
    --repo-dir)
      [[ $# -ge 2 ]] || { echo "Missing value for --repo-dir" >&2; exit 1; }
      REPO_DIR="$2"
      shift 2
      ;;
    --skip-deps)
      SKIP_DEPS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

install_deps_macos() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install Homebrew first: https://brew.sh" >&2
    exit 1
  fi
  brew install yt-dlp ffmpeg jq
}

if [[ "$SKIP_DEPS" -eq 0 ]]; then
  case "$(uname -s)" in
    Darwin)
      install_deps_macos
      ;;
    *)
      echo "Auto dependency install is only implemented for macOS." >&2
      echo "Install these manually: yt-dlp ffmpeg jq" >&2
      ;;
  esac
fi

require_cmd git

if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone https://github.com/smankoo/ai-skills.git "$REPO_DIR"
fi

mkdir -p "$TARGET_DIR"

if [[ "$INSTALL_ALL" -eq 1 ]]; then
  "$REPO_DIR/scripts/install-skill.sh" --all --target "$TARGET_DIR"
else
  IFS=',' read -r -a skills <<< "$SKILL_LIST"
  "$REPO_DIR/scripts/install-skill.sh" "${skills[@]}" --target "$TARGET_DIR"
fi

echo "Bootstrap complete."
