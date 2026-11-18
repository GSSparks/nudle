# nudle/intents/music.py

**Role:** Intent handler for local music playback (play, stop, skip).

## Overview

Communicates with `audio/backend.py` over HTTP. Playback is performed by `mpg123` running in a subprocess, managed in a dedicated daemon thread.

## Keyword Matching

Three keyword sets with fuzzy fallbacks:

| Set | Keywords | Fuzzy map examples |
|-----|----------|--------------------|
| Play | play, put, hear, listen, start, queue | place→play, pay→play |
| Stop | stop, pause, halt, quiet, shut | top→stop, shop→stop |
| Skip | next, skip, forward | snip→skip |

`can_handle()` checks all three sets plus generic `"music"`, `"song"`, `"album"` keywords.  
`correct_command_word()` applies fuzzy corrections to every word in the utterance.  
`normalize_text()` only corrects the *first* word via exact dictionary lookup (less aggressive than `correct_command_word`).

## Slot Extraction

`extract_slots(text)` looks for:
- `album <name>` or `genre <name>` as prefixed keywords
- `by <artist>` for artist disambiguation
- Falls through to `extract_free_text()` which strips filler words

`parse_music_prompt(text)` tries the extracted raw text against the backend as album, genre, artist, and song in sequence, returning the first hit.

## Playback

`play_tracks(tracks_list)` runs in a background thread:
- Iterates the track list, spawning `mpg123 -q -v <url>` per track
- Checks `stop_event` and `next_event` every 100 ms
- `player_process` is the currently running `subprocess.Popen` handle (used by ducking)

`stop_current_playback()` sets both events, terminates the process, and joins the thread.  
`skip_to_next_track()` sets `next_event` only, so the loop advances.

## Backend Interaction

`check_playlist_exists(prompt)` does a dry-run POST to verify a playlist exists (used during intent parsing without side effects).  
`fetch_playlist(prompt, interrupt=True)` fetches tracks and starts the player thread.

## Intent Cooldown

`LAST_PLAY_TIME` + `INTENT_COOLDOWN = 2 s` prevents double-firing from rapid commands.

## Module-level Globals

| Name | Purpose |
|------|---------|
| `player_process` | Current mpg123 `Popen` handle (read by ducking) |
| `player_thread` | Background playback thread |
| `tracks` | Current playlist |
| `stop_event` / `next_event` | Threading events for control |
| `player_lock` | Mutex for `player_process` access |
