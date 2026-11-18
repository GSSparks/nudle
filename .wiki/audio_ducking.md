# nudle/audio/ducking.py

**Role:** Pauses and resumes background audio players during TTS or command capture.

## Mechanism

Uses POSIX signals:
- `duck()` sends `SIGSTOP` to any live `music.player_process` or `radio.player_process`, recording which processes were stopped in `_ducked_players`
- `unduck()` sends `SIGCONT` to everything in `_ducked_players`, then clears the list

Both functions check `p.poll() is None` before signaling to avoid errors on already-dead processes.

## Usage in main.py

`duck()` is called immediately after a wake word is confirmed (before TTS greet and STT).  
`unduck()` is called at every exit point from the command handler: after speaking a response, after enrollment, and on timeout.

## Notes

- Both `music` and `radio` player handles are imported directly from their intent modules (the modules expose `player_process` as a module-level global)
- If neither player is running, `duck()`/`unduck()` are no-ops
