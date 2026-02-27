#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Install AI skills from this repo into a target skills directory.

Usage:
  install-skill.sh --all [--target DIR]
  install-skill.sh <skill-name> [<skill-name> ...] [--target DIR]
  install-skill.sh --list

Options:
  --all           Install all skills in ./skills
  --target DIR    Destination skills directory (default: ~/.codex/skills)
  --list          Print available skills and exit
  -h, --help      Show help

Examples:
  ./scripts/install-skill.sh --all
  ./scripts/install-skill.sh youtube-carplay-chapter-album
  ./scripts/install-skill.sh --all --target ~/.codex/skills
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
TARGET_DIR="$HOME/.codex/skills"
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
      TARGET_DIR="$2"
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

mkdir -p "$TARGET_DIR"

for skill in "${SKILLS_TO_INSTALL[@]}"; do
  if [[ ! -d "$SKILLS_DIR/$skill" ]]; then
    echo "Skill not found: $skill" >&2
    exit 1
  fi
  rm -rf "$TARGET_DIR/$skill"
  cp -R "$SKILLS_DIR/$skill" "$TARGET_DIR/$skill"
  echo "Installed: $skill -> $TARGET_DIR/$skill"
done

echo "Done."
