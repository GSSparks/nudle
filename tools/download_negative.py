#!/usr/bin/env python3
"""
Download negative training data for wake word training.

Sources:
  librispeech  — LibriSpeech test-clean from OpenSLR (~346 MB, ~5000 clips of speech)
  esc50        — ESC-50 environmental noise from GitHub (~600 MB, 2000 noise clips)

Usage (run from project root):
  python tools/download_negative.py --source librispeech
  python tools/download_negative.py --source esc50
  python tools/download_negative.py --source librispeech --source esc50

No extra pip dependencies — uses only soundfile + scipy already in requirements.txt.
"""
import argparse
import os
import sys
import tarfile
import tempfile
import urllib.request
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

NEGATIVE_DIR = Path("training_data/negative")
SAMPLE_RATE  = 16000

LIBRISPEECH_URL = "https://www.openslr.org/resources/12/test-clean.tar.gz"
ESC50_URL       = "https://github.com/karoldvl/ESC-50/archive/refs/heads/master.zip"


def _to_mono_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        g = gcd(SAMPLE_RATE, sr)
        audio = resample_poly(audio, SAMPLE_RATE // g, sr // g)
    return audio.astype(np.float32)


def _progress(block: int, block_size: int, total: int):
    done = block * block_size
    pct  = min(done * 100 // total, 100) if total > 0 else 0
    mb   = done / 1_000_000
    tot  = total / 1_000_000
    print(f"\r  {pct:3d}%  {mb:.1f} / {tot:.1f} MB", end="", flush=True)


def _download(url: str, dest: Path):
    print(f"  {url}")
    urllib.request.urlretrieve(url, str(dest), reporthook=_progress)
    print()


def from_librispeech():
    """Download LibriSpeech test-clean, convert FLAC → 16kHz mono WAV, split into 2 s chunks."""
    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = len(list(NEGATIVE_DIR.glob("*.wav")))
    print(f"📥  LibriSpeech test-clean  (~346 MB)")

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
        tmp = Path(f.name)

    try:
        _download(LIBRISPEECH_URL, tmp)
        print("  Extracting FLAC files...")

        idx    = existing
        saved  = 0
        chunk  = SAMPLE_RATE * 2  # 2-second clips

        with tarfile.open(tmp, "r:gz") as tar:
            flac_members = [m for m in tar.getmembers() if m.name.endswith(".flac")]
            print(f"  Found {len(flac_members)} FLAC clips, converting...")

            for member in flac_members:
                f_obj = tar.extractfile(member)
                if f_obj is None:
                    continue
                try:
                    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as ftmp:
                        ftmp.write(f_obj.read())
                        flac_path = ftmp.name
                    audio, sr = sf.read(flac_path)
                    os.unlink(flac_path)
                except Exception:
                    continue

                audio = _to_mono_16k(audio, sr)
                for start in range(0, len(audio) - chunk, chunk):
                    out = NEGATIVE_DIR / f"{idx:06d}.wav"
                    sf.write(str(out), audio[start:start + chunk], SAMPLE_RATE)
                    idx  += 1
                    saved += 1

        print(f"✅  Saved {saved} clips to {NEGATIVE_DIR}  (total: {idx})")

    finally:
        try: tmp.unlink()
        except: pass


def from_esc50():
    """Download ESC-50 environmental noise dataset (~600 MB, 2000 clips)."""
    import zipfile

    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = len(list(NEGATIVE_DIR.glob("*.wav")))
    print(f"📥  ESC-50 environmental noise  (~600 MB, 2000 clips)")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        tmp = Path(f.name)

    try:
        _download(ESC50_URL, tmp)
        print("  Extracting...")

        idx   = existing
        saved = 0
        with zipfile.ZipFile(tmp, "r") as zf:
            audio_members = [m for m in zf.namelist()
                             if m.endswith(".wav") and "/audio/" in m]
            print(f"  Found {len(audio_members)} WAV clips, converting...")

            with tempfile.TemporaryDirectory() as extract_dir:
                for member in audio_members:
                    zf.extract(member, extract_dir)
                    wav_path = Path(extract_dir) / member
                    try:
                        audio, sr = sf.read(str(wav_path))
                        audio = _to_mono_16k(audio, sr)
                        out = NEGATIVE_DIR / f"{idx:06d}.wav"
                        sf.write(str(out), audio, SAMPLE_RATE)
                        idx  += 1
                        saved += 1
                    except Exception:
                        continue

        print(f"✅  Saved {saved} ESC-50 clips to {NEGATIVE_DIR}  (total: {idx})")

    finally:
        try: tmp.unlink()
        except: pass


def main():
    p = argparse.ArgumentParser(description="Download negative training data")
    p.add_argument("--source", choices=["librispeech", "esc50"],
                   action="append", dest="sources",
                   help="Data source (can specify multiple times)")
    args = p.parse_args()

    sources = args.sources or ["librispeech"]

    for source in sources:
        if source == "librispeech":
            from_librispeech()
        elif source == "esc50":
            from_esc50()


if __name__ == "__main__":
    main()
