#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  build_carplay_album.sh "<youtube-url>" [output_root]

Example:
  build_carplay_album.sh "https://www.youtube.com/watch?v=sBQtMysE_Mo" "/Users/sumeet/Downloads"
EOF
}

require_cmd() {
  local c="$1"
  command -v "$c" >/dev/null 2>&1 || {
    echo "Missing required command: $c" >&2
    exit 1
  }
}

sanitize_name() {
  # Keep file names Finder-friendly and deterministic.
  sed 's#[/:*?"<>|]# - #g; s/[[:space:]]\+/ /g; s/^ *//; s/ *$//'
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -lt 1 ]]; then
  usage
  exit 0
fi

require_cmd yt-dlp
require_cmd jq
require_cmd ffmpeg
require_cmd ffprobe
require_cmd awk
require_cmd sed

url="$1"
output_root="${2:-$HOME/Downloads}"
mkdir -p "$output_root"

workdir="$(mktemp -d "${output_root%/}/.ytcarplay.XXXXXX")"
cleanup() {
  if [[ "${KEEP_WORK:-0}" != "1" ]]; then
    rm -rf "$workdir"
  else
    echo "KEEP_WORK=1 set, retaining: $workdir"
  fi
}
trap cleanup EXIT

info_json="$workdir/info.json"
yt-dlp --dump-single-json "$url" > "$info_json"

chapters_count="$(jq '.chapters | length' "$info_json")"
has_chapters=1
if [[ "$chapters_count" -eq 0 ]]; then
  has_chapters=0
fi

raw_album="$(jq -r '.title' "$info_json")"
# Prefer "part1: part2" when YouTube title uses "part1 | part2 | ...".
album="$(printf '%s' "$raw_album" | awk -F ' \\| ' '{if (NF>=2) print $1 ": " $2; else print $1}' | sanitize_name)"
artist="$(jq -r '.uploader // "Unknown Artist"' "$info_json" | sanitize_name)"
upload_date="$(jq -r '.upload_date // ""' "$info_json")"
year="${upload_date:0:4}"
if [[ -z "$year" ]]; then
  year="$(date +%Y)"
fi

album_dir="${output_root%/}/${album} (Album)"
mkdir -p "$album_dir/artwork"

audio_src="$workdir/audio_source.webm"
video_src="$workdir/preview_video.mp4"

yt-dlp -f "bestaudio" -o "$audio_src" "$url"
yt-dlp -f "18/b[height<=360]" -o "$video_src" "$url"

genre="${GENRE:-Electronic}"
audio_duration="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$audio_src")"
track_total="$chapters_count"
if [[ "$has_chapters" -eq 0 ]]; then
  track_total=1
fi

for idx in $(seq 1 "$track_total"); do
  if [[ "$has_chapters" -eq 1 ]]; then
    j=$((idx - 1))
    start="$(jq -r ".chapters[$j].start_time" "$info_json")"
    end="$(jq -r ".chapters[$j].end_time" "$info_json")"
    title="$(jq -r ".chapters[$j].title" "$info_json")"

    if [[ "$end" == "null" || -z "$end" ]]; then
      if [[ "$idx" -lt "$track_total" ]]; then
        end="$(jq -r ".chapters[$idx].start_time" "$info_json")"
      else
        end="$audio_duration"
      fi
    fi
  else
    start="0"
    end="$audio_duration"
    title="$(jq -r '.track // .title // "Track 1"' "$info_json")"
  fi

  track_num="$(printf '%02d' "$idx")"
  safe_title="$(printf '%s' "$title" | sanitize_name)"
  art_path="$album_dir/artwork/${track_num} - ${safe_title}.jpg"
  out_path="$album_dir/${track_num} - ${safe_title}.mp3"

  midpoint="$(awk -v s="$start" -v e="$end" 'BEGIN {m=s+((e-s)/2); if (m<s+3) m=s+3; printf "%.3f", m}')"

  ffmpeg -y -ss "$midpoint" -i "$video_src" -frames:v 1 -q:v 2 "$workdir/frame.jpg" >/dev/null 2>&1

  ffmpeg -y -i "$workdir/frame.jpg" -filter_complex \
    "[0:v]scale=1400:1400,boxblur=20:10[bg];[0:v]scale=1400:-1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuvj420p" \
    -q:v 2 "$art_path" >/dev/null 2>&1

  ffmpeg -y -ss "$start" -to "$end" -i "$audio_src" -i "$art_path" \
    -map 0:a -map 1:v \
    -c:a libmp3lame -q:a 0 \
    -c:v mjpeg \
    -id3v2_version 3 -write_id3v1 1 \
    -metadata title="$title" \
    -metadata artist="$artist" \
    -metadata album="$album" \
    -metadata album_artist="$artist" \
    -metadata genre="$genre" \
    -metadata date="$year" \
    -metadata track="${idx}/${track_total}" \
    -metadata comment="Source: $url" \
    -metadata:s:v title="Cover (front)" \
    -metadata:s:v comment="Cover (front)" \
    "$out_path" >/dev/null 2>&1

  echo "Created: $(basename "$out_path")"
done

echo "Album ready: $album_dir"
