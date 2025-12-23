#!/usr/bin/env bash
set -e

echo "🥣 Installing nudle dependencies for Raspberry Pi 400 (Debian Bookworm)"

# -----------------------------
# System packages
# -----------------------------
sudo apt update

sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  cmake \
  pkg-config \
  portaudio19-dev \
  ffmpeg \
  alsa-utils \
  espeak \
  mpg123 \
  git \
  curl 

# -----------------------------
# Python virtual environment
# -----------------------------
if [ ! -d ".venv" ]; then
  echo "🐍 Creating Python virtual environment"
  python3 -m venv .venv
fi

source .venv/bin/activate

pip install --upgrade pip setuptools wheel

# -----------------------------
# Python packages
# -----------------------------
echo "📦 Installing Python packages"

pip install \
  webrtcvad \
  sounddevice \
  numpy \
  scipy \
  requests \
  pyttsx3 \
  uvicorn \
  fastapi \
  mutagen \
  watchdog

# -----------------------------
# Speech-to-text (Pi 400 capable)
# -----------------------------
echo "🧠 Installing faster-whisper (CPU-only)"

pip install \
  faster-whisper \
  ctranslate2

# -----------------------------
# Text-to-speech
# -----------------------------
echo "🗣️ Installing Piper TTS (system package)"

sudo apt install -y piper-tts

# -----------------------------
# Audio permissions
# -----------------------------
sudo usermod -aG audio $USER

echo ""
echo "✅ nudle dependencies installed for Pi 400"
echo "ℹ️ Activate with: source .venv/bin/activate"
echo "🔁 Reboot recommended for audio permissions"

