import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import time


class SpeakerVerifier:
    def __init__(self, registry, threshold=0.70, auto_learn_threshold=0.80, max_embeddings=50):
        self.registry = registry
        self.threshold = threshold
        self.auto_learn_threshold = auto_learn_threshold
        self.max_embeddings = max_embeddings
        self.last_verification = {}

    def _normalize_embedding(self, emb):
        """Ensure embedding is 1D and normalized."""
        emb = np.asarray(emb)
        if emb.ndim > 1:
            emb = emb.flatten()
        # Normalize to unit vector
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb

    def verify(self, embedding: np.ndarray, auto_learn=True):
        """Verify speaker and optionally add high-confidence samples."""
        embedding = self._normalize_embedding(embedding)

        best_name = None
        best_score = 0.0
        all_scores = {}

        for name, speaker in self.registry.all():
            try:
                # Normalize all reference embeddings
                refs = [self._normalize_embedding(e) for e in speaker["embeddings"]]
                if not refs:
                    continue

                # Stack into 2D array for sklearn
                refs = np.stack(refs, axis=0)  # Shape: (n_samples, embedding_dim)

                # Compute cosine similarities
                scores = cosine_similarity(embedding.reshape(1, -1), refs)[0]
                score = float(np.max(scores))
                avg_score = float(np.mean(scores))

                all_scores[name] = {"max": score, "avg": avg_score, "count": len(refs)}

                if score > best_score:
                    best_score = score
                    best_name = name
            except Exception as e:
                print(f"⚠️ Skipping {name}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Debug output
        if all_scores:
            print(f"🔍 Speaker scores: {all_scores}")

        # Auto-learning
        if auto_learn and best_name and best_score >= self.auto_learn_threshold:
            current_count = all_scores[best_name]["count"]
            last_time = self.last_verification.get(best_name, 0)
            time_since_last = time.time() - last_time

            if current_count < self.max_embeddings and time_since_last > 30:
                self.registry.add_embedding(best_name, embedding)
                self.last_verification[best_name] = time.time()
                print(f"📚 Auto-learned new sample for {best_name} (now {current_count + 1} samples, score={best_score:.3f})")

        return best_name, best_score

    def verify_with_confidence_level(self, embedding: np.ndarray):
        """Returns name, score, and confidence level description."""
        name, score = self.verify(embedding)

        if score >= 0.85:
            level = "very high"
        elif score >= 0.75:
            level = "high"
        elif score >= 0.65:
            level = "medium"
        elif score >= 0.50:
            level = "low"
        else:
            level = "very low"

        return name, score, level
