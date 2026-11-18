# Infrastructure and Setup

## flake.nix

Nix flake providing the development shell (`nix develop`).

Provides:
- Python 3.11 + pip + virtualenv
- System audio libraries: `portaudio`, `libffi`, `ffmpeg`, `alsa-utils`
- TTS: `espeak-classic`, `piper-tts`
- Audio player: `mpg123`
- Build tools: `pkg-config`, `curl`, `git`

Shell hook behavior:
- Sets `OPENWAKEWORD_USE_PYTHON_TFLITE=1`
- Extends `LD_LIBRARY_PATH` with portaudio, libffi, espeak libs
- Auto-creates `.venv` if absent and activates it

nixpkgs pin: `nixos-24.05`

## install_nudle_pi400.sh

Bash installer for Raspberry Pi 400 (Debian Bookworm / apt).

Installs system packages:
- `python3-venv`, `python3-pip`, `python3-dev`, `build-essential`, `cmake`
- `portaudio19-dev`, `ffmpeg`, `alsa-utils`, `espeak`, `mpg123`

Creates `.venv` and installs Python packages:
- `webrtcvad`, `sounddevice`, `numpy`, `scipy`, `requests`, `pyttsx3`
- `uvicorn`, `fastapi`, `mutagen`, `watchdog`
- `faster-whisper`, `ctranslate2`
- `piper-tts` (via apt)

Also adds the current user to the `audio` group.

## nudle/requirements.txt

Canonical Python dependency list for `pip install -r requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| torch | 2.1.2 | Speaker embedding model |
| torchaudio | 2.1.2 | WAV loading for embeddings |
| soundfile | latest | WAV write for embedding |
| scikit-learn | latest | Cosine similarity in verifier |
| openwakeword | >=0.6.0 | Wake word detection |
| faster-whisper | >=0.6.1 | Speech-to-text |
| pyannote.audio | 3.1.1 | Speaker embedding model |
| sounddevice | >=0.4.7 | Microphone input |
| numpy | >=1.25,<2.0 | Audio math |
| piper-tts | >=0.1.0 | Neural TTS |
| pytz | >=2023.3 | Time zone support |
| fastapi | latest | Music backend API |
| mutagen | latest | MP3 tag reading |

## .gitignore

Excludes:
- `nudle/__pycache__`, `nudle/audio/__pycache__`, etc.
- `nudle/assets/` (MP3 alarm file)
- `nudle/models/` (ML model weights)
- `nudle/tts/voices` (Piper voice ONNX files)

## Directories Not in Git

| Path | Contents |
|------|---------|
| `.venv/` | Python virtual environment (dev machine) |
| `system/` | Python venv (appears to be an alternate env) |
| `nudle311/` | Another Python venv (Python 3.11 specific) |
| `nudle/models/` | pyannote model weights (must be provided separately) |
| `~/.nudle/speakers/` | Per-user speaker embeddings (created at runtime) |
