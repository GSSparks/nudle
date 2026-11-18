# nudle/speaker/verifier.py

**Role:** Identifies a speaker by cosine similarity against registered embeddings, with optional auto-learning.

## Class: `SpeakerVerifier`

### Constructor

```python
SpeakerVerifier(registry, threshold=0.70, auto_learn_threshold=0.80, max_embeddings=50)
```

### `verify(embedding, auto_learn=True) -> (name, score)`

1. Iterates all speakers in the registry
2. Computes cosine similarity between the query embedding and every stored reference using `sklearn.metrics.pairwise.cosine_similarity`
3. Takes `max()` of per-reference scores as the speaker score
4. Tracks best name/score across all speakers
5. If `auto_learn=True` and best score >= `auto_learn_threshold` (0.80):
   - Adds the new embedding to the registry (up to `max_embeddings`)
   - Enforces a 30 s cooldown (`last_verification` dict) to avoid adding noise from the same utterance

Returns `(best_name, best_score)`. If no speakers are registered, returns `(None, 0.0)`.

### `verify_with_confidence_level(embedding) -> (name, score, level)`

Wraps `verify()` and adds a human-readable confidence label:
- >= 0.85: "very high"
- >= 0.75: "high"
- >= 0.65: "medium"
- >= 0.50: "low"
- < 0.50: "very low"

## Thresholds in Context

| Threshold | Used in |
|-----------|---------|
| 0.70 | Minimum to greet the speaker by name |
| 0.80 | Auto-learn new sample |
| 0.50 | "Possible speaker" log message |

## Notes

- Verification does not require a minimum registered sample count
- `all_scores` dict is printed to stdout for every verification call (debug aid)
