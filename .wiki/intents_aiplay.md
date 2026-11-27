# nudle/intents/aiplay.py

**Role:** Intent handler for AI-generated music playlists sourced from Ollama and played via YouTube.

## Overview

When the user asks for music by mood, genre, or vague description ("play some chill jazz", "put on something for studying"), this intent asks a local Ollama LLM to generate a playlist, resolves each track to a YouTube audio URL via yt-dlp, and streams them through mpv.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `NUDLE_OLLAMA_URL` | `http://192.168.1.189:11434` | Ollama API base URL |
| `NUDLE_LLM_MODEL` | `qwen3.5:4b` | Model name |
| `NUDLE_AIPLAY_TRACKS` | `5` | Number of tracks per playlist |

## `can_handle()`

Returns True when:
- A play verb is present (`play`, `put on`, `queue`, `give me`, `find me`, `i want to hear`, `i want to listen`)
- AND at least one of: a vague phrase (`me some`, `something`, `some music for`, `a playlist`) OR a mood/genre word (see `_MOOD_WORDS`)
- AND the word `"by"` is NOT present (artist-specific requests go to local music)

Also returns True for stop/skip/pause commands when the aiplay player is currently running.

## Playlist Generation (`_ask_ollama()`)

Sends a structured prompt to Ollama requesting a JSON object:
```json
{"playlist": ["Song Title - Artist Name", ...]}
```

Augments the prompt with the speaker's past music prompts from `prefs.music_context()` so the model can personalize suggestions.

Uses `"think": False` and a 45-second timeout to avoid delays from reasoning models.

## YouTube Resolution (`_search_youtube()`)

Runs `yt-dlp -f bestaudio "ytsearch1:<song>"` per track in a `ThreadPoolExecutor` (up to 4 workers) to resolve audio URLs in parallel. Tracks that fail resolution are skipped.

## Playback (`_build_and_play()`)

Runs in a background daemon thread. After all URLs are resolved:
1. Calls `_speak_fn("Playing N tracks.")` to announce
2. Spawns `mpv --no-video --really-quiet <urls...>`
3. Waits for mpv to exit
4. Records the prompt via `prefs.record_music(speaker, prompt, completed=(returncode == 0))`
   - Completed playlist: weight 2
   - Stopped/killed: weight 1

## Player Control

`stop_playback()` terminates the mpv process. `handle()` calls `stop_playback()` and also stops `music.stop_current_playback()` and `radio.stop_radio()` before starting a new playlist, so only one audio source is ever active.

## Module-level Globals

| Name | Purpose |
|------|---------|
| `player_process` | Current mpv `Popen` handle (read by piper.py for ducking) |
| `_speak_fn` | Injected by `main.py` via `set_speak_fn()` at startup |
| `_active_speaker` | Set by `set_speaker()` from main.py before each command |
