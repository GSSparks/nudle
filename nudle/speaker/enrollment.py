import time
import tempfile
import numpy as np
import soundfile as sf


class SpeakerEnrollment:
    def __init__(self, embedder, registry, speech_collector, sample_rate=16000):
        """
        embedder: SpeakerEmbedder
        registry: SpeakerRegistry
        speech_collector: callable(seconds) -> pcm_bytes
        """
        self.embedder = embedder
        self.registry = registry
        self.collect_speech = speech_collector
        self.sample_rate = sample_rate

    def enroll(self, name: str, samples=3, seconds=2.0):
        """
        Enroll a speaker by capturing multiple clean speech samples.
        """
        name = name.lower()

        for i in range(samples):
            print(f"🎤 Enrollment sample {i+1}/{samples} — please speak...")

            # Small delay to avoid capturing prompt audio
            time.sleep(0.3)

            pcm = self.collect_speech(seconds)
            if not pcm:
                print("⚠️ No audio captured, skipping sample")
                continue

            # Convert PCM → WAV (temporary)
            audio = (
                np.frombuffer(pcm, np.int16)
                .astype(np.float32) / 32768.0
            )

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
                sf.write(f.name, audio, self.sample_rate)
                emb = self.embedder.embed(f.name)

            self.registry.add_embedding(name, emb)
            print(f"✅ Captured sample {i+1}")

        print(f"🧠 Speaker '{name}' enrolled with {samples} samples")
        return name
