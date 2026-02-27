---
name: youtube-carplay-chapter-album
description: Convert a chaptered YouTube video into a native iPhone/CarPlay-ready MP3 album with one file per chapter, full metadata, track numbering, and embedded per-track artwork. Use when the user provides a YouTube URL and asks for chapter splitting, album organization, clean tags, and polished cover art.
---

# Youtube Carplay Chapter Album

Build one MP3 per YouTube chapter, embed chapter-specific cover art, and write album metadata that sorts correctly in Apple Music and CarPlay.

## Execute

Run:

```bash
scripts/build_carplay_album.sh "<youtube-url>" [output_root]
```

Defaults:
- `output_root` defaults to `/Users/sumeet/Downloads`
- Album folder name format: `<album title> (Album)`
- Artwork style: full frame centered on a square canvas with subtle blurred padding (prevents face-only crops)

## Produce

The script must:
- Read YouTube metadata and chapters with `yt-dlp --dump-single-json`
- Download `bestaudio` for MP3 quality and a compact video stream for artwork capture
- Create one MP3 per chapter in track order (`01`, `02`, ...)
- Fallback to one single-track MP3 when no chapters exist
- Embed ID3 tags: `title`, `artist`, `album`, `album_artist`, `track n/total`, `genre`, `date`, `comment`
- Embed one unique `1400x1400` cover image per track
- Use iPhone-friendly ID3 settings: `-id3v2_version 3 -write_id3v1 1`

## Verify

After generation, verify each track contains:
- Audio stream + attached image stream
- Valid `track` tag (e.g., `3/8`)
- Expected title and album tags

Use:

```bash
ffprobe -v error -show_entries format_tags=title,album,track -show_entries stream=codec_type,width,height "<track>.mp3"
```

## Troubleshoot

- If disk space is low, delete temporary work directories created by this skill.
- If Apple Music shows stale art, remove the imported album from Music and re-import the generated folder.
