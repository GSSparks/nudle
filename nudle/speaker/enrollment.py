import time
import tempfile
import numpy as np
import soundfile as sf


class SpeakerEnrollment:
    def __init__(self, embedder, registry, speech_collector, sample_rate=16000):
        self.embedder = embedder
        self.registry = registry
        self.collect_speech = speech_collector
        self.sample_rate = sample_rate

    def _normalize_embedding(self, emb):
        """Ensure embedding is 1D and normalized."""
        emb = np.asarray(emb)
        if emb.ndim > 1:
            emb = emb.flatten()
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb

    def enroll(self, name: str, samples=4, seconds=4.0):
        """Enhanced enrollment with quality checks."""
        name = name.lower()
        embeddings = []

        print(f"🎤 Starting enrollment for {name}")
        print(f"   Please speak naturally for {seconds} seconds per sample")
        print(f"   Tips: Vary your tone, volume, and phrasing across samples")

        successful_samples = 0
        attempts = 0
        max_attempts = samples + 3  # Allow a few retries

        while successful_samples < samples and attempts < max_attempts:
            attempts += 1
            print(f"\n📝 Sample {successful_samples+1}/{samples} - Recording in 1 second...")
            time.sleep(1.0)

            pcm = self.collect_speech(seconds)
            if not pcm:
                print("⚠️ No audio captured, please try again")
                continue

            # Convert PCM → embedding
            audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0

            # Check audio quality
            energy = np.sqrt(np.mean(audio ** 2))
            if energy < 0.01:
                print(f"⚠️ Audio too quiet (energy={energy:.4f}), please speak louder")
                continue

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
                sf.write(f.name, audio, self.sample_rate)
                emb = self.embedder.embed(f.name)

            # Normalize embedding
            emb = self._normalize_embedding(emb)

            # Quality check against existing embeddings
            if embeddings:
                similarities = [np.dot(emb, prev_emb) for prev_emb in embeddings]
                avg_sim = np.mean(similarities)

                if avg_sim < 0.3:
                    print(f"⚠️ Sample seems inconsistent (similarity={avg_sim:.2f})")
                    print(f"   This might be background noise or a different voice")
                    continue

                print(f"✅ Sample {successful_samples+1} captured (similarity: {avg_sim:.2f})")
            else:
                print(f"✅ Sample {successful_samples+1} captured (baseline)")

            embeddings.append(emb)
            self.registry.add_embedding(name, emb)
            successful_samples += 1

        if successful_samples < samples:
            print(f"⚠️ Only captured {successful_samples}/{samples} samples")
            return None

        print(f"\n🧠 Enrollment complete: '{name}' registered with {len(embeddings)} samples")

        # Show average intra-speaker similarity
        if len(embeddings) > 1:
            sims = []
            for i in range(len(embeddings)):
                for j in range(i+1, len(embeddings)):
                    sim = np.dot(embeddings[i], embeddings[j])
                    sims.append(sim)
            avg_intra_sim = np.mean(sims)
            print(f"   Average intra-speaker similarity: {avg_intra_sim:.3f}")
            if avg_intra_sim < 0.6:
                print(f"   ⚠️ Low similarity - samples may be inconsistent")
            elif avg_intra_sim < 0.7:
                print(f"   ⚙️ Moderate similarity - enrollment acceptable")
            else:
                print(f"   ✅ Good similarity - strong enrollment!")

        return name
