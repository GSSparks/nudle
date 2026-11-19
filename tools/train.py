#!/usr/bin/env python3
"""
Train the Hey Noodle wake word model using OpenWakeWord's Model class.

Usage:
  python tools/generate_samples.py        # generate positive audio
  python tools/download_negative.py       # download negative audio
  python tools/train.py                   # train and export ONNX

Output: nudle/assets/Hey_Noodle.onnx
"""
import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
POSITIVE_DIR = PROJECT_ROOT / "training_data" / "positive"
NEGATIVE_DIR = PROJECT_ROOT / "training_data" / "negative"
OUTPUT_PATH  = PROJECT_ROOT / "nudle" / "assets" / "Hey_Noodle.onnx"

SAMPLE_RATE   = 16000
N_FEATURE_FRAMES = 16          # OWW input: (batch, 16, 96)
EMBEDDING_DIM    = 96
N_EPOCHS      = 150
BATCH_SIZE    = 256
LR            = 1e-3


# ---------------------------------------------------------------------------
# Ensure training deps are installed
# ---------------------------------------------------------------------------

def _require(pkg, import_name=None):
    import_name = import_name or pkg
    try:
        __import__(import_name)
    except (ImportError, SystemError):
        print(f"  Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])


def install_deps():
    print("🔧  Checking training dependencies...")
    _require("torchinfo")
    _require("torchmetrics")
    _require("onnx<1.16", "onnx")
    print("   ✅  OK")


# ---------------------------------------------------------------------------
# Feature extraction via OWW's AudioFeatures
# ---------------------------------------------------------------------------

def extract_features(wav_paths, label: int, af):
    """
    Process WAV files through OWW's AudioFeatures pipeline.
    Returns X (N, 16, 96) float32 and y (N,) int arrays.
    """
    import soundfile as sf
    import numpy as np
    from math import gcd
    from scipy.signal import resample_poly

    X, y = [], []

    for path in wav_paths:
        try:
            audio, sr = sf.read(str(path))
        except Exception:
            continue

        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SAMPLE_RATE:
            g = gcd(SAMPLE_RATE, sr)
            audio = resample_poly(audio, SAMPLE_RATE // g, sr // g)

        audio_int16 = (audio * 32767).clip(-32768, 32767).astype("int16")

        # Feed through AudioFeatures in 1280-sample chunks
        chunk = 1280
        for i in range(0, len(audio_int16) - chunk, chunk):
            af(audio_int16[i:i + chunk])

        # Collect all available feature windows
        n_frames = af.feature_buffer.shape[0]
        for start in range(0, n_frames - N_FEATURE_FRAMES, N_FEATURE_FRAMES):
            feat = af.feature_buffer[start:start + N_FEATURE_FRAMES].astype("float32")
            if feat.shape == (N_FEATURE_FRAMES, EMBEDDING_DIM):
                X.append(feat)
                y.append(label)

    return X, y


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train():
    install_deps()

    import numpy as np
    import torch
    from torch import nn, optim
    from torch.utils.data import DataLoader, TensorDataset

    from openwakeword.utils import AudioFeatures

    print("=" * 60)
    print("  Hey Noodle — wake word training")
    print("=" * 60)

    pos_clips = sorted(POSITIVE_DIR.glob("*.wav"))
    neg_clips  = sorted(NEGATIVE_DIR.rglob("*.wav"))

    if not pos_clips:
        print(f"❌  No positive samples in {POSITIVE_DIR}")
        print("    Run:  python tools/generate_samples.py")
        sys.exit(1)
    if not neg_clips:
        print(f"❌  No negative samples in {NEGATIVE_DIR}")
        print("    Run:  python tools/download_negative.py")
        sys.exit(1)

    print(f"📊  Positive clips : {len(pos_clips)}")
    print(f"📊  Negative clips : {len(neg_clips)}")
    print()

    # Feature extraction
    af = AudioFeatures(device="cpu")
    print("🔊  Extracting features from positive samples...")
    X_pos, y_pos = extract_features(pos_clips, label=1, af=af)
    print(f"   {len(X_pos)} windows extracted")

    # Reset buffer between positive and negative
    af = AudioFeatures(device="cpu")
    print("🔊  Extracting features from negative samples...")
    # Sample negatives to avoid huge imbalance (max 10× positives)
    import random
    neg_sample = random.sample(neg_clips, min(len(neg_clips), len(pos_clips) * 10))
    X_neg, y_neg = extract_features(neg_sample, label=0, af=af)
    print(f"   {len(X_neg)} windows extracted")

    if not X_pos or not X_neg:
        print("❌  Feature extraction produced no data. Check audio files.")
        sys.exit(1)

    # Build tensors
    X = torch.tensor(np.array(X_pos + X_neg), dtype=torch.float32)
    y = torch.tensor(np.array(y_pos  + y_neg), dtype=torch.float32).unsqueeze(1)

    # Shuffle
    idx = torch.randperm(len(X))
    X, y = X[idx], y[idx]

    dataset = TensorDataset(X, y)
    loader  = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    print(f"\n🧠  Training OWW model — {len(X)} samples, {N_EPOCHS} epochs")
    print(f"   Positive: {sum(y_pos)}  Negative: {sum(1 for _ in y_neg)}")
    print()

    # Replicate OWW's DNN architecture (from openwakeword/train.py Model class)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    layer_dim = 128

    class FCNBlock(nn.Module):
        def __init__(self, dim):
            super().__init__()
            self.fc = nn.Linear(dim, dim)
            self.relu = nn.ReLU()
            self.ln = nn.LayerNorm(dim)
        def forward(self, x):
            return self.relu(self.ln(self.fc(x)))

    class WakeWordNet(nn.Module):
        def __init__(self):
            super().__init__()
            flat = N_FEATURE_FRAMES * EMBEDDING_DIM
            self.flatten  = nn.Flatten()
            self.layer1   = nn.Linear(flat, layer_dim)
            self.relu1    = nn.ReLU()
            self.ln1      = nn.LayerNorm(layer_dim)
            self.block    = FCNBlock(layer_dim)
            self.out      = nn.Linear(layer_dim, 1)
            self.sigmoid  = nn.Sigmoid()
        def forward(self, x):
            x = self.relu1(self.ln1(self.layer1(self.flatten(x))))
            x = self.block(x)
            return self.sigmoid(self.out(x))

    model = WakeWordNet().to(device)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=LR)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=50, gamma=0.5)

    best_loss = float("inf")
    best_state = None

    for epoch in range(1, N_EPOCHS + 1):
        model.train()
        total_loss = 0.0
        correct = 0

        for X_batch, y_batch in loader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)

            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            correct += ((pred > 0.5).float() == y_batch).sum().item()

        scheduler.step()
        avg_loss = total_loss / len(loader)
        acc = correct / len(X) * 100

        if epoch % 10 == 0 or epoch == 1:
            print(f"  Epoch {epoch:3d}/{N_EPOCHS}  loss={avg_loss:.4f}  acc={acc:.1f}%")

        if avg_loss < best_loss:
            best_loss = avg_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    print(f"\n✅  Training complete  (best loss={best_loss:.4f})")

    # Restore best weights
    if best_state:
        model.load_state_dict(best_state)

    # Export to ONNX
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    dummy = torch.zeros(1, N_FEATURE_FRAMES, EMBEDDING_DIM).to(device)

    torch.onnx.export(
        model,
        dummy,
        str(OUTPUT_PATH),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        opset_version=12,
    )

    print(f"✅  Saved: {OUTPUT_PATH}")
    print("    Nüdle will auto-detect it on next run.")
    print()
    print("    Test it:")
    print("      python nudle/main.py")


if __name__ == "__main__":
    train()
