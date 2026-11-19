# tts/piper.py
import subprocess
import shutil
import os
import signal
import io
import math
import tempfile
import soundfile as sf
import sounddevice as sd
from scipy.signal import resample_poly
from intents import music
from intents import radio

VOICE_PATH = os.environ.get("PIPER_VOICE", "").strip() or \
    os.path.join(os.path.dirname(__file__), "voices", "en_US-lessac-medium.onnx")

PIPER_BIN = os.environ.get("PIPER_BIN", "").strip() or shutil.which("piper")
PAPLAY_BIN = shutil.which("paplay")
PW_PLAY_BIN = shutil.which("pw-play")


def _find_sd_output_device():
    env_device = os.environ.get("NUDLE_OUTPUT_DEVICE", "").strip()
    if env_device:
        idx = int(env_device)
        print(f"🔊 TTS output: #{idx} {sd.query_devices(idx)['name']} (NUDLE_OUTPUT_DEVICE)")
        return idx
    return None

_SD_OUTPUT_DEVICE = _find_sd_output_device()


def speak(text: str):
    if not PIPER_BIN:
        raise RuntimeError("piper binary not found")
    if not os.path.exists(VOICE_PATH):
        raise RuntimeError(f"Piper voice not found: {VOICE_PATH}")

    if PAPLAY_BIN:
        _speak_paplay(text)
    elif PW_PLAY_BIN:
        _speak_pw_play(text)
    else:
        _speak_sounddevice(text)


def _speak_paplay(text: str):
    """Pipe piper WAV directly into paplay — routes through PipeWire default sink."""
    proc = subprocess.Popen(
        [PIPER_BIN, "--model", VOICE_PATH, "--output_file", "-", "--quiet"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    player = subprocess.Popen(
        [PAPLAY_BIN],
        stdin=proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.stdout.close()
    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()
    player.wait()
    proc.wait()


def _speak_pw_play(text: str):
    """Generate WAV to temp file, play through PipeWire default sink via pw-play."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        subprocess.run(
            [PIPER_BIN, "--model", VOICE_PATH, "--output_file", tmp_path, "--quiet"],
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [PW_PLAY_BIN, tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _speak_sounddevice(text: str):
    """Fallback: sounddevice playback (no cutoff, but device may not be PipeWire)."""
    result = subprocess.run(
        [PIPER_BIN, "--model", VOICE_PATH, "--output_file", "-", "--quiet"],
        input=text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    audio, sr = sf.read(io.BytesIO(result.stdout), dtype="float32")
    device_sr = int(sd.query_devices(_SD_OUTPUT_DEVICE, kind="output")["default_samplerate"])
    if sr != device_sr:
        g = math.gcd(sr, device_sr)
        audio = resample_poly(audio, device_sr // g, sr // g).astype("float32")
        sr = device_sr
    sd.play(audio, sr, device=_SD_OUTPUT_DEVICE)
    sd.wait()


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
