# Nüdle — CLAUDE.md

Nüdle is a fully local, offline voice assistant for Linux/NixOS. Wake word + Whisper STT + intent routing + Piper TTS. No cloud.

## Project Layout

```
nudle/
  main.py                  # Entry point and main loop — read this first
  audio/
    backend.py             # FastAPI music library server (separate process)
    ducking.py             # SIGSTOP/SIGCONT ducking of media players
    player.py              # Empty stub
  intents/
    music.py               # Local music playback (mpg123 + backend HTTP)
    radio.py               # Internet radio (mpv)
    time.py                # Time, timers, alarms
    weather.py             # wttr.in weather
    gag.py                 # Hardcoded joke responses
    enroll_speaker.py      # "my name is …" trigger detection
    status.py              # Empty stub
  speaker/
    embedding.py           # pyannote speaker embeddings
    registry.py            # ~/.nudle/speakers/{name}.json storage
    verifier.py            # Cosine similarity verification + auto-learn
    enrollment.py          # Interactive multi-sample enrollment
  state/
    conversation.py        # ConversationState class (defined but unused)
  tts/
    __init__.py            # Engine selection (piper / espeak fallback)
    piper.py               # Piper TTS via subprocess + aplay
    espeak.py              # espeak fallback
    voices/                # Gitignored — ONNX voice model lives here
  assets/
    lo-fi-alarm-clock-243766.mp3   # Alarm sound (gitignored)
  requirements.txt
flake.nix                  # Nix dev shell
install_nudle_pi400.sh     # Raspberry Pi 400 apt installer
.wiki/                     # Per-file documentation (see .wiki/index.md)
```

## Development Environment

**NixOS (primary):** `nix develop` — provides Python 3.11, portaudio, piper-tts, espeak, mpg123, ffmpeg.

**Raspberry Pi 400:** run `bash install_nudle_pi400.sh`

**Activate venv:** `source .venv/bin/activate`

**Run the assistant:** `cd nudle && python main.py`

**Run the music backend:** `cd nudle && uvicorn audio.backend:app --host 0.0.0.0 --port 8000`

## Runtime Prerequisites (not in git)

| Path | What it is | How to get it |
|------|-----------|---------------|
| `nudle/models/pyannote_embedding/pytorch_model.bin` | Speaker embedding model | Download from pyannote hub |
| `nudle/assets/Hey_Noodle.onnx` | Wake word model | Custom trained or swap for a stock OWW model |
| `nudle/tts/voices/en_US-lessac-medium.onnx` | Piper voice | `piper --download-voice en_US-lessac-medium` |
| `~/.nudle/speakers/` | Enrolled speaker profiles | Created automatically at runtime |

## Intent System

Adding a new intent: create `nudle/intents/myintent.py` with:
```python
def can_handle(text: str) -> bool: ...
def handle(text: str) -> str | dict: ...
```
Then add it to the import list and `handle_command()` loop in `main.py`.

Returning a `dict` from `handle()` triggers multi-turn conversation mode. The dict must have:
```python
{"prompt": "...", "intent": "<name>", "expect": "<slot>"}
```
Then implement `handle_followup(text, context)` and register it in `main.py`'s `handle_followup()`.

## Key Constants (main.py)

| Constant | Value | Change if … |
|----------|-------|-------------|
| `WHISPER_MODEL` | `tiny.en` | You need better accuracy (use `base.en`) |
| `WAKE_CONFIDENCE` | 0.75 | Too many/few false wakes |
| `WAKE_COOLDOWN` | 20 s | Re-triggering too quickly |
| `COMMAND_TIMEOUT` | 2.0 s | Commands get cut off |
| `CONVERSATION_TIMEOUT` | 5 s | Follow-up window too short/long |

## Speaker Recognition Thresholds

| Threshold | Value | Effect |
|-----------|-------|--------|
| Verify (greet) | 0.70 | Lower = more false positives |
| Auto-learn | 0.80 | Lower = learns noise; higher = learns slowly |
| Enrollment consistency | 0.40 | Lower = accepts more variable samples |

Speaker data lives in `~/.nudle/speakers/`. Delete a `.json` file to clear a speaker.

## TTS Engine

Controlled by env var `RESON_TTS` (default: `piper`). Set `RESON_TTS=espeak` to skip Piper.  
Piper uses `aplay` for output; adjust `-r 22050 -f S16_LE` flags in `tts/piper.py` if your audio hardware needs different settings.

## Known Issues

- `intents/music.py:play_tracks()` references undefined `BACKEND_HOST` for relative URLs — not hit in normal use since the backend returns full URLs
- `intents/time.py`'s internal `speak()` is a print-only stub; timer/alarm completion is silent to the user
- Wake word path is hardcoded to `/home/gsparks/nudle/nudle/assets/Hey_Noodle.onnx`
- Weather ZIP is hardcoded to `46711` in `intents/weather.py`
- `state/conversation.py` and `audio/player.py` and `intents/status.py` are empty stubs

## Full Documentation

See `.wiki/index.md` for per-file documentation of every module.
