# nudle/tts/

**Role:** Text-to-speech engine abstraction with Piper (primary) and espeak (fallback).

## tts/__init__.py

Selects and loads the TTS engine at import time. The engine is controlled by the environment variable `RESON_TTS` (default: `"piper"`).

Load order:
1. Try `piper` - imports `tts/piper.py`, runs a test call with `" "` (single space)
2. If Piper fails (import error or runtime error) → falls back to `espeak`
3. If espeak also fails → installs a no-op lambda that prints to stdout

After loading, `tts.speak` is a callable `(text: str) -> None`.

## tts/piper.py

Uses the Piper neural TTS binary with the bundled ONNX voice model.

**Voice model:** `tts/voices/en_US-lessac-medium.onnx` (gitignored)  
Override with env var `PIPER_VOICE`.

**Synthesis pipeline:**
```
piper --model <voice> --output-raw  →  stdout (raw PCM)
aplay -r 22050 -f S16_LE -t raw    →  audio hardware
```

Both processes run in parallel via `subprocess.Popen`; `audio.communicate()` blocks until playback completes.

`speak_ducked(text)` is a higher-level function that SIGSTOP/SIGCONT active players around the TTS call. This is not used by `main.py` (which calls `duck()`/`unduck()` from `audio/ducking.py` directly), but available for callers that don't have access to the ducking module.

## tts/espeak.py

Minimal fallback: runs `espeak -s 165 -v en-us <text>` synchronously.

## Notes

- `piper` and `aplay` are located via `shutil.which()` at import time; if either is missing Piper will raise `RuntimeError` and trigger the fallback
- The voice ONNX file and its `.json` sidecar are gitignored; they must be present on disk at runtime
