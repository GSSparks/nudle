import json
import pathlib
import numpy as np

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

    # ✅ REQUIRED BY SpeakerVerifier
    def all(self):
        """
        Returns iterable of (speaker_name, speaker_dict)
        """
        return self.speakers.items()

    def save(self, name: str):
        path = SPEAKER_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(self.speakers[name], f, indent=2)

    def add_embedding(self, name: str, embedding: np.ndarray):
        name = name.lower()

        self.speakers.setdefault(
            name,
            {
                "name": name,
                "embeddings": [],
            },
        )

        # Ensure 1D embedding
        embedding = np.asarray(embedding).reshape(-1)

        self.speakers[name]["embeddings"].append(embedding.tolist())
        self.save(name)

    def get_embeddings(self, name: str):
        name = name.lower()
        if name not in self.speakers:
            return []

        return [np.array(e) for e in self.speakers[name]["embeddings"]]

    def has_speaker(self, name: str) -> bool:
        return name.lower() in self.speakers
