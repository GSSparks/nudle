# nudle/speaker/enrollment.py

**Role:** Collects multiple voice samples to enroll a new speaker.

## Class: `SpeakerEnrollment`

### Constructor

```python
SpeakerEnrollment(embedder, registry, speech_collector, sample_rate=16000)
```

`speech_collector` is a callable (passed in from `main.py`) that captures raw PCM for a given duration.

### `enroll(name, samples=4, seconds=4.0) -> str | None`

Runs an interactive enrollment loop:
1. Waits 1 second, then calls `collect_speech(seconds)`
2. Checks audio energy (threshold 0.01 RMS); rejects quiet audio
3. Writes to a temp WAV, runs `SpeakerEmbedder.embed()`
4. Checks cosine similarity with previously collected samples (threshold 0.3); rejects inconsistent audio
5. Saves the embedding via `SpeakerRegistry.add_embedding()`
6. Repeats until `samples` good samples are collected (up to `samples + 3` attempts)

Returns the name on success, `None` if fewer than `samples` could be collected.

After enrollment, prints intra-speaker similarity statistics.

## Relationship to `main.py`

`main.py` does not use `SpeakerEnrollment.enroll()` directly. Instead, it has its own `enroll_speaker_safe()` function which wraps `SpeakerEnrollment` with higher quality thresholds (5 samples, consistency check at 0.4, plus an immediate verification test after enrollment).

`SpeakerEnrollment` is instantiated in `main.py` and passed `collect_speech_window` as the collector.
