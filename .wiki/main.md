# nudle/main.py

**Role:** Entry point and main event loop for the Nüdle voice assistant.

## Responsibilities

- Opens a continuous `sounddevice` InputStream at 16 kHz / int16
- Feeds 80 ms frames (1280 samples) into the openWakeWord model
- On wake word detection (score >= 0.75, cooldown 20 s), ducks audio and transitions to command capture
- Collects 2 seconds of post-wake audio, runs speaker verification and Whisper STT
- Routes transcribed text to the intent chain in `handle_command()`
- Supports a conversational follow-up loop (5 s timeout) for multi-turn intents (timer, alarm)
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

## State Machine (globals)

```
wake_latched  →  wake_active  →  awaiting_command
                                        ↓
                               speaker verify + STT
                                        ↓
                             handle_command() / enroll
                                        ↓
                          [optional] conversation_active
```

`tts_active` is a guard that prevents the wake-word model from triggering during TTS playback.

## Important Functions

| Function | Description |
|----------|-------------|
| `audio_callback()` | sounddevice callback; pushes raw int16 chunks onto `audio_queue` |
| `flush_audio_queue()` | Drains queue to prevent stale audio from carrying over |
| `collect_command_audio(timeout)` | Collects and concatenates audio for the given window |
| `detect_speech_segments()` | Energy-based VAD; returns `has_speech`, `speech_ratio` |
| `embed_from_pcm()` | Quality-checks audio then calls `SpeakerEmbedder.embed()` |
| `preprocess_onnx_frame()` | Converts raw int16 frame to log-mel spectrogram for ONNX wake model |
| `transcribe()` | Runs faster-whisper on a PCM buffer |
| `handle_command()` | Iterates intent modules; returns string or dict (multi-turn) |
| `handle_followup()` | Dispatches follow-up responses to `time_intent` |
| `enroll_speaker_safe()` | Collects 5 high-quality samples with consistency checks |
| `main()` | Infinite audio loop with the full state machine |

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
