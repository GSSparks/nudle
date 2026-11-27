# nudle/main.py

**Role:** Entry point and main event loop for the Nüdle voice assistant.

## Responsibilities

- Opens a continuous `sounddevice` InputStream at 16 kHz / int16
- Feeds 80 ms frames (1280 samples) into the openWakeWord model
- On wake word detection (score >= 0.75, cooldown 20 s), ducks audio and validates the interrupt (barge-in suppression)
- Collects 2 seconds of post-wake audio, runs speaker verification and Whisper STT
- Routes transcribed text to the intent chain in `handle_command()`
- Supports a conversational follow-up loop (5 s timeout) for multi-turn intents
- Handles speaker enrollment in-band when it hears "my name is …"

## Key Constants

| Name | Value | Purpose |
|------|-------|---------|
| `SAMPLE_RATE` | 16000 | Audio sample rate |
| `OW_FRAME_SIZE` | 1280 | Samples per openWakeWord frame (80 ms) |
| `WHISPER_MODEL` | `tiny.en` | Whisper model variant |
| `WAKE_CONFIDENCE` | 0.75 | Minimum score to trigger wake |
| `WAKE_COOLDOWN` | 20 s | Minimum time between wake events |
| `COMMAND_TIMEOUT` | 2.0 s | Audio collection window after wake |
| `CONVERSATION_TIMEOUT` | 5 s | Idle time before conversation ends |
| `BARGE_IN_SPEAKER_MIN` | 0.35 | Minimum speaker score to accept a barge-in |
| `BARGE_IN_SPEECH_MIN` | 0.15 | Minimum speech ratio to accept a barge-in |

## State Machine (globals)

```
wake_latched  →  barge-in validation (1 s)
                        |
               speaker score >= 0.35
               speech ratio >= 0.15?
                        |
                   wake_active  →  collect_command_audio()
                                        |
                               speaker verify + STT
                                        |
                             handle_command() / enroll
                                        |
                          [optional] conversation_active
```

`tts_active` is a guard that enables barge-in checking during TTS playback. Only audio that passes the speaker/speech validation thresholds is accepted as a real interrupt, preventing Nüdle from hearing its own voice and re-triggering.

## Important Functions

| Function | Description |
|----------|-------------|
| `audio_callback()` | sounddevice callback; pushes raw int16 chunks onto `audio_queue` |
| `flush_audio_queue()` | Drains queue to prevent stale audio from carrying over |
| `collect_command_audio(timeout)` | Collects and concatenates audio for the given window |
| `detect_speech_segments()` | Silero VAD; returns `has_speech`, `speech_ratio` |
| `embed_from_pcm()` | Quality-checks audio then calls `SpeakerEmbedder.embed()` |
| `preprocess_onnx_frame()` | Converts raw int16 frame to log-mel spectrogram for ONNX wake model |
| `transcribe()` | Runs faster-whisper on a PCM buffer |
| `speak_safe()` | Sets `tts_active`, speaks, clears `tts_active` and flushes the audio queue |
| `handle_command()` | Iterates intent modules; dispatches LLM route results; returns str or dict (multi-turn) |
| `handle_followup()` | Dispatches follow-up responses to `time_intent`, with aiplay redirect detection |
| `enroll_speaker_safe()` | Collects 5 high-quality samples with consistency checks |
| `main()` | Infinite audio loop with the full state machine |

## Intent Routing in `handle_command()`

The routing chain is:
1. **Lights** — checked first via `lights_intent.can_handle()` (keyword match)
2. **Stop/skip intercept** — if "stop", "pause", "skip", "next" are present, all players are halted before routing continues
3. **Music** — `music_intent.can_handle()` returns True; then `aiplay_intent.can_handle()` decides whether to send to AI playlist or local library
4. **Radio, time, weather, gag, enroll** — keyword-based handlers checked in order
5. **LLM fallback** — `llm_intent.handle()` is called; if it returns a `dict` with `"route"`, `_LLM_ROUTE_MAP` dispatches to the appropriate intent

`_LLM_ROUTE_MAP` maps route keys (`"lights"`, `"music"`, `"weather"`, `"time"`, `"radio"`) to their handler functions.

## Music Disambiguation

When the music intent fires but all query candidates have equal values (e.g. the query could be genre or song title), `handle_command()` returns a multi-turn follow-up prompt asking for clarification. Any follow-up response containing an aiplay redirect phrase ("playlist", "youtube", "ai", "random") is sent to `aiplay_intent` instead of `music_intent`.

## Startup Sequence

```python
aiplay_intent.set_speak_fn(speak_safe)   # aiplay needs to announce playback
lights_intent.discover_lights()           # cache HA entities once at boot
```

Per-command, before `handle_command()`:
```python
aiplay_intent.set_speaker(speaker_name)
lights_intent.set_speaker(speaker_name)
```

## Wake Word Model

Loaded from `/home/gsparks/nudle/nudle/assets/Hey_Noodle.onnx` via openWakeWord.
When `inference_framework == "onnx"`, frames are manually preprocessed to 16-band log-mel spectrograms (96 time steps) before `ow_model.predict()`.

## Speaker Recognition Flow

1. `embed_from_pcm()` applies a pre-emphasis filter, normalizes, and writes a temp WAV
2. `SpeakerEmbedder.embed()` runs pyannote to get a 1-D unit-norm embedding
3. `SpeakerVerifier.verify()` cosine-scores against all registered speakers
4. Score >= 0.70: greet by name; 0.50–0.69: log as possible; < 0.50: unknown
5. Auto-learns new samples when score >= 0.80 (up to 50 total per speaker)

## Audio Hardware

Looks for a `wm8960` device (Waveshare WM8960 HAT) on startup; falls back to system default.

## Dependencies

`main.py` imports from every other module in the project.
