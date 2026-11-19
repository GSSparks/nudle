#!/usr/bin/env python3
"""
Generate positive training samples for the "hey noodle" wake word.

Outputs WAV files to training_data/positive/.
Run from the project root:
  python tools/generate_samples.py

Requires: piper (nix develop) and/or espeak, plus soundfile + scipy.
"""
import os
import sys
import shutil
import subprocess
import tempfile
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample, resample_poly

PHRASE = "hey noodle"
SAMPLE_RATE = 16000
OUTPUT_DIR = Path("training_data/positive")

PIPER_BIN  = os.environ.get("PIPER_BIN", "").strip() or shutil.which("piper")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "").strip() or str(
    Path(__file__).parent.parent / "nudle/tts/voices/en_US-lessac-medium.onnx"
)
ESPEAK_BIN = shutil.which("espeak") or shutil.which("espeak-ng")


# ---------------------------------------------------------------------------
# Base sample generators
# ---------------------------------------------------------------------------

def _to_mono_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        g = gcd(SAMPLE_RATE, sr)
        audio = resample_poly(audio, SAMPLE_RATE // g, sr // g)
    return audio.astype(np.float32)


def piper_sample(length_scale: float = 1.0) -> np.ndarray | None:
    if not PIPER_BIN or not os.path.exists(PIPER_VOICE):
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        r = subprocess.run(
            [PIPER_BIN, "--model", PIPER_VOICE, "--output_file", wav_path,
             "--length_scale", str(length_scale), "--quiet"],
            input=PHRASE.encode(), capture_output=True,
        )
        if r.returncode != 0:
            return None
        audio, sr = sf.read(wav_path)
        return _to_mono_16k(audio, sr)
    except Exception as e:
        print(f"  piper error: {e}")
        return None
    finally:
        try: os.unlink(wav_path)
        except: pass


def espeak_sample(voice: str = "en-us", speed: int = 160, pitch: int = 50) -> np.ndarray | None:
    if not ESPEAK_BIN:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        r = subprocess.run(
            [ESPEAK_BIN, "-v", voice, "-s", str(speed), "-p", str(pitch),
             "-w", wav_path, PHRASE],
            capture_output=True,
        )
        if r.returncode != 0:
            return None
        audio, sr = sf.read(wav_path)
        return _to_mono_16k(audio, sr)
    except Exception as e:
        print(f"  espeak error: {e}")
        return None
    finally:
        try: os.unlink(wav_path)
        except: pass


# ---------------------------------------------------------------------------
# Augmentation
# ---------------------------------------------------------------------------

def augment(audio: np.ndarray, speed: float = 1.0, noise: float = 0.0,
            gain: float = 1.0) -> np.ndarray:
    if speed != 1.0:
        new_len = int(len(audio) / speed)
        audio = resample(audio, new_len)
    if noise > 0:
        audio = audio + np.random.randn(len(audio)).astype(np.float32) * noise
    audio = audio * gain
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    return audio


AUGMENTATIONS = [
    {"speed": 1.00, "noise": 0.000, "gain": 1.0},
    {"speed": 0.90, "noise": 0.002, "gain": 0.9},
    {"speed": 0.95, "noise": 0.003, "gain": 1.0},
    {"speed": 1.05, "noise": 0.002, "gain": 1.1},
    {"speed": 1.10, "noise": 0.004, "gain": 0.8},
    {"speed": 1.15, "noise": 0.001, "gain": 1.0},
    {"speed": 0.85, "noise": 0.005, "gain": 0.95},
]

PIPER_RATES    = [0.75, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20, 1.30]
ESPEAK_CONFIGS = [
    ("en-us",  130, 40), ("en-us",  150, 50), ("en-us",  170, 55),
    ("en-us",  190, 45), ("en-us",  200, 60), ("en-gb",  140, 50),
    ("en-gb",  160, 55), ("en-gb",  175, 48), ("en",     145, 52),
    ("en",     165, 50), ("en-029", 155, 50), ("en-029", 170, 45),
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(OUTPUT_DIR.glob("*.wav"))
    idx = len(existing)

    if not PIPER_BIN and not ESPEAK_BIN:
        print("❌  No TTS available. Set PIPER_BIN or install espeak.")
        sys.exit(1)

    print(f"Phrase      : '{PHRASE}'")
    print(f"Output      : {OUTPUT_DIR}")
    print(f"Existing    : {idx} samples")
    print(f"piper       : {PIPER_BIN or 'not found'}")
    print(f"espeak      : {ESPEAK_BIN or 'not found'}")
    print()

    generated = 0

    if PIPER_BIN and os.path.exists(PIPER_VOICE):
        print(f"🎙  Piper ({len(PIPER_RATES)} rates × {len(AUGMENTATIONS)} augs "
              f"= {len(PIPER_RATES) * len(AUGMENTATIONS)} samples)")
        for rate in PIPER_RATES:
            base = piper_sample(length_scale=rate)
            if base is None:
                print(f"   ⚠ piper rate={rate} failed, skipping")
                continue
            for aug in AUGMENTATIONS:
                sf.write(str(OUTPUT_DIR / f"{idx:05d}.wav"),
                         augment(base.copy(), **aug), SAMPLE_RATE)
                idx += 1
                generated += 1
        print(f"   → {len(PIPER_RATES) * len(AUGMENTATIONS)} generated")

    if ESPEAK_BIN:
        print(f"🗣  espeak ({len(ESPEAK_CONFIGS)} voices × {len(AUGMENTATIONS)} augs "
              f"= {len(ESPEAK_CONFIGS) * len(AUGMENTATIONS)} samples)")
        for voice, speed, pitch in ESPEAK_CONFIGS:
            base = espeak_sample(voice=voice, speed=speed, pitch=pitch)
            if base is None:
                print(f"   ⚠ espeak voice={voice} speed={speed} failed, skipping")
                continue
            for aug in AUGMENTATIONS:
                sf.write(str(OUTPUT_DIR / f"{idx:05d}.wav"),
                         augment(base.copy(), **aug), SAMPLE_RATE)
                idx += 1
                generated += 1
        print(f"   → {len(ESPEAK_CONFIGS) * len(AUGMENTATIONS)} generated")

    total = idx
    print(f"\n✅  Total positive samples: {total}")
    if total < 500:
        print(f"⚠   Minimum recommended is 500 (have {total}).")
        print("    Consider adding more TTS voices.")
    else:
        print("    Ready for training.")


if __name__ == "__main__":
    main()
