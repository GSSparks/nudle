import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


class SpeakerVerifier:
    def __init__(self, registry, threshold=0.75):
        self.registry = registry
        self.threshold = threshold

    def verify(self, embedding: np.ndarray):
        best_name = None
        best_score = 0.0

        for name, speaker in self.registry.all():
            try:
                refs = [np.asarray(e).reshape(-1) for e in speaker["embeddings"]]
                refs = np.stack(refs, axis=0)  # safe 2D array now
            except Exception as e:
                print(f"⚠️ Skipping {name}: {e}")
                continue

            from sklearn.metrics.pairwise import cosine_similarity
            scores = cosine_similarity(embedding.reshape(1, -1), refs)[0]
            score = float(np.max(scores))
            if score > best_score:
                best_score = score
                best_name = name

        return best_name, best_score

