from pyannote.audio import Model
import torch
import numpy as np
import torchaudio

if not hasattr(torchaudio, "AudioMetaData"):
    class AudioMetaData:
        pass
    torchaudio.AudioMetaData = AudioMetaData


class SpeakerEmbedder:
    def __init__(self, device="cpu"):
        self.device = device

        self.model = Model.from_pretrained(
            local_dir="./models/pyannote_embedding",
            checkpoint="./models/pyannote_embedding/pytorch_model.bin",
            strict=False,
        ).to(device).eval()

    def embed(self, wav_path: str, debug=False) -> np.ndarray:
        """Generate speaker embedding with strict shape control."""
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
