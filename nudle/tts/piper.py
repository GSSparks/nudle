# tts/piper.py
import subprocess
import shutil
import os
import signal
from intents import music
from intents import radio

# Path to your Piper voice
VOICE_PATH = os.environ.get(
    "PIPER_VOICE",
    "tts/voices/en_US-hfc_female-medium.onnx"
)

PIPER_BIN = shutil.which("piper")
APLAY_BIN = shutil.which("aplay")


def speak(text: str):
    if not PIPER_BIN or not APLAY_BIN:
        raise RuntimeError("piper or aplay not found")

    if not os.path.exists(VOICE_PATH):
        raise RuntimeError(f"Piper voice not found: {VOICE_PATH}")

    proc = subprocess.Popen(
        [
            PIPER_BIN,
            "--model", VOICE_PATH,
            "--output-raw",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    audio = subprocess.Popen(
        [
            APLAY_BIN,
            "-r", "22050",
            "-f", "S16_LE",
            "-t", "raw",
        ],
        stdin=proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()
    audio.communicate()


def _get_active_players():
    """
    Return a list of active player processes (mpg123, mpv, etc).
    """
    procs = []

    for p in [music.player_process, radio.player_process]:
        if p and p.poll() is None:
            procs.append(p)

    return procs


def speak_ducked(text: str):
    """
    Duck any playing music or radio, speak text, then resume playback.
    """
    active_players = _get_active_players()

    # Pause all players
    for p in active_players:
        try:
            p.send_signal(signal.SIGSTOP)
        except Exception as e:
            print(f"⚠️ Failed to pause player: {e}")

    # Speak
    try:
        speak(text)
    except Exception as e:
        print(f"⚠️ TTS failed: {e}")
        print(f"(TTS fail) {text}")

    # Resume all players
    for p in active_players:
        try:
            p.send_signal(signal.SIGCONT)
        except Exception as e:
            print(f"⚠️ Failed to resume player: {e}")
