# nudle/speaker/embedding.py

**Role:** Generates speaker embeddings from WAV files using pyannote.audio.

## Class: `SpeakerEmbedder`

### Constructor

```python
SpeakerEmbedder(device="cpu")
```

Loads a pyannote embedding model from `./models/pyannote_embedding/pytorch_model.bin` (local, no internet required). Uses `strict=False` to tolerate checkpoint/architecture mismatches.

### `embed(wav_path, debug=False) -> np.ndarray`

1. Loads WAV with `torchaudio`
2. Converts multi-channel to mono (mean across channels)
3. Ensures shape `(batch=1, channel=1, samples)`
4. Runs the model in `torch.no_grad()` context
5. Flattens output to 1-D, normalizes to unit vector
6. Returns a `np.ndarray` of shape `(embedding_dim,)` with L2 norm = 1

## Compatibility Fix

Patches `torchaudio.AudioMetaData` if missing (older torchaudio versions).

## Notes

- Model is loaded onto CPU; no GPU required
- All embeddings are unit-normalized, so dot product == cosine similarity
- The model checkpoint is local and gitignored (`nudle/models/` is in `.gitignore`)
