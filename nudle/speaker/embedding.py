from pyannote.audio import Model
import torch
import numpy as np
import torchaudio

# Compatibility shim for older pyannote expectations
if not hasattr(torchaudio, "AudioMetaData"):
    class AudioMetaData:
        pass
    torchaudio.AudioMetaData = AudioMetaData


class SpeakerEmbedder:
    def __init__(self, device="cpu"):
        self.device = device

        # Load locally downloaded pyannote embedding model
        self.model = Model.from_pretrained(
            local_dir="./models/pyannote_embedding",
            checkpoint="./models/pyannote_embedding/pytorch_model.bin",
            strict=False,  # avoids warnings about old training versions
        ).to(device).eval()

    def embed(self, wav_path: str) -> np.ndarray:
        # Load audio
        waveform, sr = torchaudio.load(wav_path)

        # Convert multi-channel → mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Ensure shape: (batch, channel, samples)
        if waveform.dim() == 2:
            waveform = waveform.unsqueeze(0)

        waveform = waveform.to(self.device)

        with torch.no_grad():
            embedding = self.model(waveform)

        # 🔑 CRITICAL FIX:
        # Force output to strictly 1D (embedding_dim,)
        embedding = embedding.squeeze().reshape(-1)
        embedding = embedding / np.linalg.norm(embedding)

        return embedding.cpu().numpy()
