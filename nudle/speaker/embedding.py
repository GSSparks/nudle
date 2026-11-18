from pyannote.audio import Model
import torch
import numpy as np
import torchaudio
import os

if not hasattr(torchaudio, "AudioMetaData"):
    class AudioMetaData:
        pass
    torchaudio.AudioMetaData = AudioMetaData

CHECKPOINT = os.path.join(os.path.dirname(__file__), "..", "models", "pyannote_embedding", "pytorch_model.bin")


class SpeakerEmbedder:
    def __init__(self, device="cpu"):
        self.device = device
        self.model = None

        checkpoint = os.path.normpath(CHECKPOINT)
        if not os.path.exists(checkpoint):
            print(f"⚠️ Speaker model not found: {checkpoint}")
            print("   Speaker recognition disabled. See README to download the model.")
            return

        try:
            self.model = Model.from_pretrained(checkpoint, strict=False).to(device).eval()
            print("✅ Speaker embedding model loaded")
        except Exception as e:
            print(f"⚠️ Failed to load speaker model: {e}")
            print("   Speaker recognition disabled.")

    def embed(self, wav_path: str, debug=False):
        """Generate speaker embedding with strict shape control."""
        if self.model is None:
            return None
        waveform, sr = torchaudio.load(wav_path)

        if debug:
            print(f"   Audio: {waveform.shape}, sample_rate={sr}")

        # Convert multi-channel → mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Ensure shape: (batch, channel, samples)
        if waveform.dim() == 2:
            waveform = waveform.unsqueeze(0)

        waveform = waveform.to(self.device)

        with torch.no_grad():
            embedding = self.model(waveform)

        # CRITICAL: Force to 1D numpy array
        embedding = embedding.cpu().numpy()
        embedding = embedding.flatten()  # Ensure 1D

        if debug:
            print(f"   Embedding shape: {embedding.shape}, norm: {np.linalg.norm(embedding):.3f}")

        # Normalize to unit vector
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding
