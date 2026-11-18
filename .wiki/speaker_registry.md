# nudle/speaker/registry.py

**Role:** Persistent storage for speaker embeddings.

## Storage Layout

Embeddings are stored as JSON files in `~/.nudle/speakers/{name}.json`.

Each file has the structure:
```json
{
  "name": "gary",
  "embeddings": [[...], [...], ...],
  "created": 1700000000.0,
  "last_updated": 1700000001.0
}
```

The directory is created on first use.

## Class: `SpeakerRegistry`

### Key Methods

| Method | Description |
|--------|-------------|
| `add_embedding(name, embedding)` | Normalizes embedding, appends to list, saves JSON |
| `get_embeddings(name)` | Returns list of normalized 1-D arrays |
| `has_speaker(name)` | Boolean check |
| `get_stats(name)` | Returns count, avg/min/max intra-speaker cosine similarity, timestamps |
| `prune_embeddings(name, max_count=50)` | Keeps only the most recent N embeddings |
| `clear_speaker(name)` | Deletes the in-memory entry and the JSON file |

### `_normalize_embedding(emb)`

Internal helper used before every read/write. Flattens to 1-D and L2-normalizes. Called defensively throughout to tolerate embeddings stored before normalization was enforced.

## Notes

- Names are always lowercased before storage
- Thread safety is not explicitly handled; this is acceptable because enrollment is a blocking foreground operation
- `prune_embeddings()` is not called automatically; it must be invoked manually if needed
