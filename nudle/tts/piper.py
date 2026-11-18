# tts/piper.py
import subprocess
import shutil
import os
import signal
from intents import music
from intents import radio

VOICE_PATH = os.environ.get("PIPER_VOICE", "").strip() or \
    os.path.join(os.path.dirname(__file__), "voices", "en_US-lessac-medium.onnx")

# Prefer the binary pinned by the dev environment (Nix package), fall back to PATH
PIPER_BIN = os.environ.get("PIPER_BIN", "").strip() or shutil.which("piper")
MPV_BIN = shutil.which("mpv")


def speak(text: str):
    if not PIPER_BIN:
        raise RuntimeError("piper binary not found")
    if not MPV_BIN:
        raise RuntimeError("mpv not found")
    if not os.path.exists(VOICE_PATH):
        raise RuntimeError(f"Piper voice not found: {VOICE_PATH}")

    proc = subprocess.Popen(
        [PIPER_BIN, "--model", VOICE_PATH, "--output_file", "-", "--quiet"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    player = subprocess.Popen(
        [MPV_BIN, "--no-video", "--really-quiet", "-"],
        stdin=proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()
    player.wait()


def _get_active_players():
    return [p for p in [music.player_process, radio.player_process] if p and p.poll() is None]


def speak_ducked(text: str):
    active_players = _get_active_players()
    for p in active_players:
        try:
            p.send_signal(signal.SIGSTOP)
        except Exception as e:
            print(f"⚠️ Failed to pause player: {e}")

    try:
        speak(text)
    except Exception as e:
        print(f"⚠️ TTS failed: {e}")

    for p in active_players:
        try:
            p.send_signal(signal.SIGCONT)
        except Exception as e:
            print(f"⚠️ Failed to resume player: {e}")
