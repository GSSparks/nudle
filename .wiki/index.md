# Nüdle Wiki — Index

Nüdle is a fully local, privacy-first voice assistant running on Linux/NixOS. It wakes on a custom wake word, transcribes speech with Whisper, routes to intent handlers, and responds via Piper TTS. No cloud required.

## Architecture Overview

```
Microphone (sounddevice)
        |
        v
  [OW Frame Buffer]
        |
        v
 openWakeWord (ONNX)  ─── score >= 0.75 ──► duck() + collect_command_audio()
                                                     |
                                           SpeakerEmbedder (pyannote)
                                                     |
                                           SpeakerVerifier (cosine sim)
                                                     |
                                             Whisper STT
                                                     |
                                    ┌────────────────────────────┐
                                    │        Intent Router        │
                                    │  lights / aiplay / music /  │
                                    │  radio / time / weather /   │
                                    │  gag / enroll / llm         │
                                    └────────────────────────────┘
                                                     |
                                             Piper TTS → aplay
                                                     |
                                               unduck()
```

## Two-Process Design

The music system is split across two processes:
- **main.py** handles wake word, STT, and intent routing
- **audio/backend.py** is a FastAPI server that owns the music index and streams MP3s

They communicate over HTTP at `http://127.0.0.1:8000`.

## Wiki Pages

### Core

| File | Wiki Page | Description |
|------|-----------|-------------|
| `nudle/main.py` | [main.md](main.md) | Main loop, state machine, wake word, speaker verification |

### Audio

| File | Wiki Page | Description |
|------|-----------|-------------|
| `nudle/audio/backend.py` | [audio_backend.md](audio_backend.md) | FastAPI music library server |
| `nudle/audio/ducking.py` | [audio_ducking.md](audio_ducking.md) | SIGSTOP/SIGCONT audio ducking |

### Intents

| File | Wiki Page | Description |
|------|-----------|-------------|
| `nudle/intents/lights.py` | [intents_lights.md](intents_lights.md) | Home Assistant light control |
| `nudle/intents/aiplay.py` | [intents_aiplay.md](intents_aiplay.md) | AI-generated playlists via Ollama + YouTube |
| `nudle/intents/llm.py` | [intents_llm.md](intents_llm.md) | Ollama LLM fallback and smart intent router |
| `nudle/intents/music.py` | [intents_music.md](intents_music.md) | Local music playback via mpg123 |
| `nudle/intents/radio.py` | [intents_radio.md](intents_radio.md) | Internet radio streams via mpv |
| `nudle/intents/time.py` | [intents_time.md](intents_time.md) | Current time, timers, alarms |
| `nudle/intents/weather.py` | [intents_weather.md](intents_weather.md) | Weather via wttr.in |
| `nudle/intents/gag.py` | [intents_gag.md](intents_gag.md) | Hardcoded joke/personality responses |
| `nudle/intents/enroll_speaker.py` | [intents_enroll_speaker.md](intents_enroll_speaker.md) | "My name is …" enrollment trigger |

### Speaker Recognition

| File | Wiki Page | Description |
|------|-----------|-------------|
| `nudle/speaker/embedding.py` | [speaker_embedding.md](speaker_embedding.md) | pyannote speaker embeddings |
| `nudle/speaker/registry.py` | [speaker_registry.md](speaker_registry.md) | Persistent JSON embedding storage |
| `nudle/speaker/verifier.py` | [speaker_verifier.md](speaker_verifier.md) | Cosine similarity verification + auto-learning |
| `nudle/speaker/enrollment.py` | [speaker_enrollment.md](speaker_enrollment.md) | Interactive multi-sample enrollment |
| `nudle/speaker/preferences.py` | [speaker_preferences.md](speaker_preferences.md) | Per-user music taste and light habit storage |

### TTS

| File | Wiki Page | Description |
|------|-----------|-------------|
| `nudle/tts/__init__.py` | [tts.md](tts.md) | Engine selection (Piper or espeak fallback) |
| `nudle/tts/piper.py` | [tts.md](tts.md) | Piper neural TTS + audio ducking helper |
| `nudle/tts/espeak.py` | [tts.md](tts.md) | espeak fallback TTS |

### State

| File | Wiki Page | Description |
|------|-----------|-------------|
| `nudle/state/conversation.py` | [state_conversation.md](state_conversation.md) | ConversationState class (placeholder, not yet wired in) |

### Infrastructure

| File | Wiki Page | Description |
|------|-----------|-------------|
| `flake.nix` | [infrastructure.md](infrastructure.md) | Nix dev shell |
| `install_nudle_pi400.sh` | [infrastructure.md](infrastructure.md) | Raspberry Pi 400 installer |
| `nudle/requirements.txt` | [infrastructure.md](infrastructure.md) | Python dependencies |

## Key Design Decisions

**Wake word:** Custom `Hey_Noodle.onnx` model loaded via openWakeWord. The main loop manually preprocesses frames to log-mel spectrograms for ONNX inference rather than using the library's default pipeline.

**Barge-in suppression:** After wake word detection, 1 second of audio is collected and validated (speaker cosine score + speech ratio) before committing to an interrupt. This prevents Nüdle from hearing its own TTS output and re-triggering.

**Speaker recognition:** pyannote.audio embeddings + cosine similarity. Auto-learns new samples above 0.80 confidence. Enrollment requires 5 high-quality samples with internal consistency checks.

**Per-user preferences:** Music prompts and light room habits are stored per speaker in `~/.nudle/preferences/{name}.json`. Completed playlists are weighted 2x over stopped ones, so genuine taste rises faster.

**Intent routing:** Sequential `can_handle()` / `handle()` calls across keyword-based intents. The LLM intent (`llm.py`) is the final fallback and returns structured JSON to re-dispatch to real intents (lights, music, weather, time, radio) rather than chatting about what it cannot do.

**Music routing:** `aiplay` is checked before local music when the request is mood/genre/vague ("play some chill jazz"). Specific artist lookups ("play Radiohead") go to local music. Stop/skip kills all active players (mpg123, mpv, aiplay).

**Home Assistant lights:** Entity discovery runs at startup via `/api/states`. Lights are identified by attribute presence (brightness, color_temp) or friendly-name keywords across all non-sensor domains. Automation `_on`/`_off` pairs are discovered separately and triggered via `automation/trigger` for entities like outdoor lights that have no direct switch.

**Multi-turn conversations:** An intent can return a `dict` instead of a `str` to trigger a follow-up loop. Currently used by timers, alarms, and the music slot disambiguation flow.

**Audio ducking:** SIGSTOP/SIGCONT on player subprocesses. Avoids mixing TTS with music/radio.

**TTS engine selection:** Env var `RESON_TTS` (default `piper`). Piper is validated at startup with a live test call; espeak is the automatic fallback.

## Known Issues / TODOs

- `nudle/state/conversation.py` is defined but unused in `main.py`
- `audio/player.py` exists but is empty (1 line)
- `intents/status.py` exists but is empty (1 line)
- `intents/music.py` references `BACKEND_HOST` in `play_tracks()` but it is never defined (would raise `NameError` for relative URLs)
- Wake word model path is hardcoded to `/home/gsparks/nudle/nudle/assets/Hey_Noodle.onnx`
- Weather location is hardcoded to ZIP `46711`
- `intents/time.py`'s internal `speak()` is a stub (prints only); timer/alarm completion is silent unless main.py is restructured to listen for callbacks
