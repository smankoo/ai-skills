#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Install AI skills from this repo into a target skills directory.

Usage:
  install-skill.sh --all [--agent codex|claude|both]
  install-skill.sh <skill-name> [<skill-name> ...] [--agent codex|claude|both]
  install-skill.sh --list

Options:
  --all           Install all skills in ./skills
  --agent VALUE   Install target: codex, claude, or both (default: codex)
  --target DIR    Destination skills directory (legacy alias for codex target)
  --codex-dir DIR Override Codex skills dir (default: ~/.codex/skills)
  --claude-dir DIR Override Claude skills dir (default: ~/.claude/skills)
  --list          Print available skills and exit
  -h, --help      Show help

Examples:
  ./scripts/install-skill.sh --all
  ./scripts/install-skill.sh youtube-carplay-chapter-album
  ./scripts/install-skill.sh --all --agent both
  ./scripts/install-skill.sh youtube-carplay-chapter-album --agent claude
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
CODEX_DIR="$HOME/.codex/skills"
CLAUDE_DIR="$HOME/.claude/skills"
AGENT_TARGET="codex"
INSTALL_ALL=0
LIST_ONLY=0
SKILLS_TO_INSTALL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      INSTALL_ALL=1
      shift
      ;;
    --target)
      [[ $# -ge 2 ]] || { echo "Missing value for --target" >&2; exit 1; }
      CODEX_DIR="$2"
      shift 2
      ;;
    --codex-dir)
      [[ $# -ge 2 ]] || { echo "Missing value for --codex-dir" >&2; exit 1; }
      CODEX_DIR="$2"
      shift 2
      ;;
    --claude-dir)
      [[ $# -ge 2 ]] || { echo "Missing value for --claude-dir" >&2; exit 1; }
      CLAUDE_DIR="$2"
      shift 2
      ;;
    --agent)
      [[ $# -ge 2 ]] || { echo "Missing value for --agent" >&2; exit 1; }
      AGENT_TARGET="$2"
      shift 2
      ;;
    --list)
      LIST_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      SKILLS_TO_INSTALL+=("$1")
      shift
      ;;
  esac
done

if [[ ! -d "$SKILLS_DIR" ]]; then
  echo "Skills directory not found: $SKILLS_DIR" >&2
  exit 1
fi

AVAILABLE=()
while IFS= read -r skill_name; do
  AVAILABLE+=("$skill_name")
done < <(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)

if [[ "$LIST_ONLY" -eq 1 ]]; then
  printf '%s\n' "${AVAILABLE[@]}"
  exit 0
fi

if [[ "$INSTALL_ALL" -eq 1 ]]; then
  SKILLS_TO_INSTALL=("${AVAILABLE[@]}")
fi

if [[ "${#SKILLS_TO_INSTALL[@]}" -eq 0 ]]; then
  echo "No skills specified. Use --all, --list, or provide skill names." >&2
  usage
  exit 1
fi

case "$AGENT_TARGET" in
  codex|claude|both) ;;
  *)
    echo "Invalid --agent value: $AGENT_TARGET (use codex|claude|both)" >&2
    exit 1
    ;;
esac

if [[ "$AGENT_TARGET" == "codex" || "$AGENT_TARGET" == "both" ]]; then
  mkdir -p "$CODEX_DIR"
fi
if [[ "$AGENT_TARGET" == "claude" || "$AGENT_TARGET" == "both" ]]; then
  mkdir -p "$CLAUDE_DIR"
fi

for skill in "${SKILLS_TO_INSTALL[@]}"; do
  if [[ ! -d "$SKILLS_DIR/$skill" ]]; then
    echo "Skill not found: $skill" >&2
    exit 1
  fi
  if [[ "$AGENT_TARGET" == "codex" || "$AGENT_TARGET" == "both" ]]; then
    rm -rf "$CODEX_DIR/$skill"
    cp -R "$SKILLS_DIR/$skill" "$CODEX_DIR/$skill"
    echo "Installed (Codex):  $skill -> $CODEX_DIR/$skill"
  fi
  if [[ "$AGENT_TARGET" == "claude" || "$AGENT_TARGET" == "both" ]]; then
    rm -rf "$CLAUDE_DIR/$skill"
    cp -R "$SKILLS_DIR/$skill" "$CLAUDE_DIR/$skill"
    echo "Installed (Claude): $skill -> $CLAUDE_DIR/$skill"
  fi
done

echo "Done."
