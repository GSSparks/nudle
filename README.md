![nudle](images/Nudle_Privacy-First_Smart_Speaker.png)

**Nüdle** (pronounced *"noo-dle"*, with a German **ü**) is a local, privacy-first voice assistant designed to run entirely on your own hardware.

It listens continuously, wakes on a custom wake word, and responds to spoken commands using on-device speech recognition and text-to-speech. No cloud required (except for internet radio streams and optional AI playlist lookups via a local Ollama instance).

## Capabilities

- Wake word detection (custom OpenWakeWord model)
- Speech-to-text via Whisper (faster-whisper, CPU)
- Speaker recognition, enrollment, and per-user preferences
- Intent routing: music, AI playlists, radio, time/timers/alarms, weather, smart home lights, personality responses
- LLM fallback via Ollama for natural-language commands that don't match a keyword intent
- Home Assistant integration for light control (turn on/off/dim, room-aware, automation pairs)
- Neural text-to-speech via Piper TTS
- Barge-in suppression (Nüdle won't interrupt itself)
- Audio ducking during interaction
- Local music library server (FastAPI + mpv)

## Tech Stack

- Python 3.11
- OpenWakeWord (ONNX)
- faster-whisper
- pyannote.audio
- Piper TTS
- sounddevice + PortAudio
- FastAPI + uvicorn
- mpv / mpg123
- yt-dlp (AI playlist YouTube lookups)
- Ollama (local LLM — qwen3.5:4b or any compatible model)
- Home Assistant REST API

## Getting Started (NixOS)

### 1. Clone the repo

```bash
git clone git@github.com:GSSparks/nudle.git
cd nudle
```

### 2. Enter the dev shell

```bash
nix develop
```

This will:
- Provide all required system binaries (`mpv`, `piper`, `aplay`, `espeak`, `ffmpeg`, `yt-dlp`, etc.)
- Create a Python 3.11 venv at `.venv/` and activate it
- Install all Python dependencies from `nudle/requirements.txt`
- Start the music backend at `http://localhost:8000`
- Warn you about any missing model files

The first run takes a few minutes to install Python packages. Subsequent runs are instant unless `requirements.txt` has changed.

### 3. Provide model files

Three files are required but not included in the repo:

**Wake word model** — place your `Hey_Noodle.onnx` at:
```
nudle/assets/Hey_Noodle.onnx
```
You can substitute any OpenWakeWord-compatible `.onnx` model and update the path in `nudle/main.py`.

**Speaker embedding model** — download the pyannote wespeaker-voxceleb-resnet34-LM model weights and place them at:
```
nudle/models/pyannote_embedding/pytorch_model.bin
```

**Piper TTS voice** — download the Lessac medium voice:
```bash
mkdir -p nudle/tts/voices
piper --download-voice en_US-lessac-medium --output-dir nudle/tts/voices
```

### 4. Configure optional integrations

Create `nudle/.env` with any of the following:

```env
# Home Assistant (for light control)
NUDLE_HA_URL=https://your-ha-instance.example.com
NUDLE_HA_TOKEN=eyJ...your_long_lived_token...

# Ollama (for AI playlists and LLM intent fallback)
NUDLE_OLLAMA_URL=http://192.168.1.x:11434
NUDLE_LLM_MODEL=qwen3.5:4b

# AI playlist track count (default: 5)
NUDLE_AIPLAY_TRACKS=5
```

### 5. Run the assistant

```bash
python nudle/main.py
```

The music backend is already running from the dev shell. To restart it after making changes:

```bash
nudle-backend
```

## Getting Started (Raspberry Pi 400)

```bash
git clone git@github.com:GSSparks/nudle.git
cd nudle
bash install_nudle_pi400.sh
source .venv/bin/activate
pip install -r nudle/requirements.txt
```

Then follow steps 3–4 above to add model files and configure `.env`, and run:

```bash
python nudle/main.py
```

For the music backend on the Pi:

```bash
cd nudle && uvicorn audio.backend:app --host 0.0.0.0 --port 8000
```

## Speaker Enrollment

Say **"my name is [name]"** after the wake word. Nüdle will walk you through speaking five samples to enroll your voice. After enrollment it will immediately test recognition.

To re-enroll, say the same phrase again — the existing profile will be cleared and replaced.

Speaker profiles are stored in `~/.nudle/speakers/`. Per-user music and light preferences are stored in `~/.nudle/preferences/`.

## Music

### Local library

The music backend indexes MP3s from `/home/gsparks/server/Music` by default. Update `LOCAL_MUSIC_DIR` in `nudle/audio/backend.py` to point at your library.

Supported commands:
- "play [song title]"
- "play album [album name]"
- "play [artist name]"
- "play genre [genre]"
- "skip" / "next"
- "stop" / "pause"

### AI playlists (requires Ollama + yt-dlp)

Say something like "play some chill jazz" or "put on a relaxing playlist" and Nüdle will ask Ollama to generate a song list, resolve each track on YouTube via yt-dlp, and stream it through mpv.

Nüdle remembers which prompts you've enjoyed most. Listening through a full playlist weights your taste profile 2x more than stopping early.

Supported commands:
- "play some [mood/genre]" — e.g. "play some 80s rock"
- "put on something relaxing"
- "stop" / "pause" — stops the current AI playlist

## Home Assistant Lights (requires NUDLE_HA_URL + NUDLE_HA_TOKEN)

Nüdle discovers all controllable light entities at startup, including switches and automation on/off pairs for outdoor lights.

Supported commands:
- "turn on/off the lights"
- "turn on/off the [room] lights" — e.g. "turn off the bedroom lights"
- "dim the lights" / "brighten the lights"
- "set the lights to 50 percent"

Nüdle remembers which rooms you typically control per person.

## LLM Intent Routing (requires Ollama)

When no keyword intent matches, Nüdle forwards the transcript to a local Ollama model. The model either routes to a known intent (lights, music, weather, time, radio) by returning a structured JSON response, or answers directly in 1–2 spoken sentences for general questions.

## Adding Intents

Create `nudle/intents/myintent.py` with:

```python
def can_handle(text: str) -> bool: ...
def handle(text: str) -> str: ...
```

Then add it to the import list and the `handle_command()` loop in `nudle/main.py`.

Return a `dict` from `handle()` to trigger a conversational follow-up:

```python
return {"prompt": "How long?", "intent": "myintent", "expect": "duration"}
```

## Status

Actively under development. Not yet intended for general use.
