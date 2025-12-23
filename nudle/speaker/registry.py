import json
import pathlib
import numpy as np
import time

SPEAKER_DIR = pathlib.Path.home() / ".nudle" / "speakers"


class SpeakerRegistry:
    def __init__(self):
        SPEAKER_DIR.mkdir(parents=True, exist_ok=True)
        self.speakers = self._load_all()

    def _load_all(self):
        speakers = {}
        for file in SPEAKER_DIR.glob("*.json"):
            with open(file) as f:
                speakers[file.stem] = json.load(f)
        return speakers

    def all(self):
        return self.speakers.items()

    def save(self, name: str):
        path = SPEAKER_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(self.speakers[name], f, indent=2)

    def _normalize_embedding(self, emb):
        """Ensure embedding is 1D and normalized."""
        emb = np.asarray(emb)
        if emb.ndim > 1:
            emb = emb.flatten()
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb

    def add_embedding(self, name: str, embedding: np.ndarray):
        name = name.lower()

        self.speakers.setdefault(
            name,
            {
                "name": name,
                "embeddings": [],
                "created": time.time(),
                "last_updated": time.time(),
            },
        )

        # Ensure 1D embedding
        embedding = self._normalize_embedding(embedding)

        self.speakers[name]["embeddings"].append(embedding.tolist())
        self.speakers[name]["last_updated"] = time.time()
        self.save(name)

    def get_embeddings(self, name: str):
        name = name.lower()
        if name not in self.speakers:
            return []
        return [self._normalize_embedding(e) for e in self.speakers[name]["embeddings"]]

    def has_speaker(self, name: str) -> bool:
        return name.lower() in self.speakers

    def get_stats(self, name: str):
        """Get statistics about a speaker's embeddings."""
        name = name.lower()
        if name not in self.speakers:
            return None

        embeddings = self.get_embeddings(name)
        if not embeddings:
            return None

        # All embeddings are now guaranteed to be 1D
        similarities = []
        for i in range(len(embeddings)):
            for j in range(i+1, len(embeddings)):
                # Simple dot product (both are normalized unit vectors)
                sim = float(np.dot(embeddings[i], embeddings[j]))
                similarities.append(sim)

        return {
            "count": len(embeddings),
            "avg_similarity": np.mean(similarities) if similarities else 0,
            "min_similarity": np.min(similarities) if similarities else 0,
            "max_similarity": np.max(similarities) if similarities else 0,
            "created": self.speakers[name].get("created"),
            "last_updated": self.speakers[name].get("last_updated"),
        }

    def prune_embeddings(self, name: str, max_count=50):
        """Keep only the most recent embeddings if count exceeds max."""
        name = name.lower()
        if name not in self.speakers:
            return

        embeddings = self.speakers[name]["embeddings"]
        if len(embeddings) > max_count:
            self.speakers[name]["embeddings"] = embeddings[-max_count:]
            self.save(name)
            print(f"🔄 Pruned {name} embeddings: {len(embeddings)} → {max_count}")

    def clear_speaker(self, name: str):
        """Remove a speaker entirely and re-enroll from scratch."""
        name = name.lower()
        if name in self.speakers:
            del self.speakers[name]
            path = SPEAKER_DIR / f"{name}.json"
            if path.exists():
                path.unlink()
            print(f"🗑️ Cleared speaker: {name}")
