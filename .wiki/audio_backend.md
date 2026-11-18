# nudle/audio/backend.py

**Role:** FastAPI server that indexes and serves the local music library.

## Overview

Runs as a separate process (not imported by `main.py` at startup). The music intent (`intents/music.py`) communicates with it over HTTP at `http://127.0.0.1:8000`.

## Configuration

| Variable | Value | Purpose |
|----------|-------|---------|
| `LOCAL_MUSIC_DIR` | `/home/gsparks/server/Music` | Root of the MP3 library |
| `INDEX_FILE` | `/tmp/music_index.json` | Persistent index cache |
| `PI_HOST` | `192.168.1.213:8000` | LAN address used in returned URLs |

## Index

`background_index_library()` runs in a daemon thread on first startup (if no cache exists). It:
1. Globs all `**/*.mp3` under `LOCAL_MUSIC_DIR`
2. Reads ID3 tags via `mutagen` (title, artist, album, genre)
3. Builds a `key` field: `normalize(title) - normalize(artist)`
4. Writes the index to `INDEX_FILE` and keeps it in `LIB_INDEX` (a module-level list guarded by `INDEX_LOCK`)

If `INDEX_FILE` already exists it loads synchronously on import.

## Search

`find_by_field(field, query, cutoff=0.7)` searches by any tag field:
1. Exact match on normalized value
2. Fuzzy match via `difflib.get_close_matches`
3. Partial substring match (for titles like "Echoes - The Best of …")

`normalize(s)` lowercases, replaces `&` with `and`, strips punctuation.

## API Routes

### `POST /playlist`

Body: `{ "prompt": "<prefix>:<query>" }` where prefix is `album`, `artist`, or `genre`.  
No prefix = song search.

Returns:
```json
{
  "matched": { "type": "album", "value": "dark side of the moon" },
  "tracks": [
    { "title": "filename.mp3", "url": "http://192.168.1.213:8000/local/..." }
  ]
}
```

### `GET /local/{path}`

Streams the MP3 file at `LOCAL_MUSIC_DIR/{path}` as `audio/mpeg`.  
Path is URL-decoded and sanitized with `os.path.normpath`.

## Notes

- Thread safety: `LIB_INDEX` is accessed via `INDEX_LOCK`; `snapshot_index()` returns a copy
- Indexing is guarded by the `INDEXING` boolean to prevent duplicate runs
- CORS is fully open (`allow_origins=["*"]`) for LAN use
