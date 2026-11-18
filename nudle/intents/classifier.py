import numpy as np

INTENT_EXAMPLES = {
    "music": [
        "play some music",
        "play bluegrass",
        "put on some jazz",
        "stop the music",
        "pause the music",
        "skip this song",
        "next track",
        "play the album dark side of the moon",
        "play something by johnny cash",
        "I want to listen to country music",
        "queue up some rock",
        "play some songs",
        "I want to hear some music",
        "turn on some music",
        "play music",
    ],
    "radio": [
        "play the radio",
        "turn on the radio",
        "play internet radio",
        "stream a radio station",
        "tune in to a station",
        "play a radio station",
    ],
    "weather": [
        "what is the weather",
        "what is the temperature outside",
        "how is the weather today",
        "will it rain tomorrow",
        "what is the forecast",
        "is it cold outside",
        "weather today",
        "how hot is it",
        "do I need a jacket",
        "what is the weather like",
    ],
    "time": [
        "what time is it",
        "set a timer for five minutes",
        "wake me up at seven",
        "set an alarm for six AM",
        "cancel my alarm",
        "what is the time",
        "timer for ten minutes",
        "remind me in an hour",
        "how much time is left on my timer",
    ],
    "gag": [
        "you suck",
        "you are terrible",
        "you are useless",
        "you are stupid",
        "you are dumb",
        "you are the worst",
        "I hate you",
        "that was awful",
        "you are an idiot",
    ],
    "enroll": [
        "my name is gary",
        "my name is john",
        "call me sarah",
        "I am michael",
        "remember my name",
        "my name is",
    ],
}

CONFIDENCE_THRESHOLD = 0.35


class IntentClassifier:
    def __init__(self):
        self.model = None
        self.centroids = {}
        self._load()

    def _load(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            self._build_centroids()
            print("✅ Intent classifier loaded (all-MiniLM-L6-v2)")
        except Exception as e:
            print(f"⚠️ Intent classifier unavailable: {e}")
            print("   Falling back to keyword matching.")

    def _build_centroids(self):
        for intent, phrases in INTENT_EXAMPLES.items():
            vecs = self.model.encode(phrases, convert_to_numpy=True)
            centroid = vecs.mean(axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            self.centroids[intent] = centroid

    def classify(self, text: str) -> tuple:
        if self.model is None:
            return "unknown", 0.0

        vec = self.model.encode([text], convert_to_numpy=True)[0]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        best_intent, best_score = "unknown", -1.0
        for intent, centroid in self.centroids.items():
            score = float(np.dot(vec, centroid))
            if score > best_score:
                best_score = score
                best_intent = intent

        if best_score < CONFIDENCE_THRESHOLD:
            return "unknown", best_score
        return best_intent, best_score
