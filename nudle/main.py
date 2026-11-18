#!/usr/bin/env python3
import os
import warnings
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
import queue
import sounddevice as sd
import numpy as np
import time
import tempfile
import soundfile as sf
import librosa
from scipy import signal

from faster_whisper import WhisperModel

warnings.filterwarnings("ignore", message="torchaudio._backend.set_audio_backend")

# --- Local imports ---
from tts import speak
from audio.ducking import duck, unduck
from intents import radio, music, weather, gag
from intents import time as time_intent

# ---------------- openWakeWord ----------------
import openwakeword
from openwakeword.model import Model

# ---------------- Speaker recognition ----------------
from speaker.embedding import SpeakerEmbedder
from speaker.registry import SpeakerRegistry
from speaker.verifier import SpeakerVerifier
from speaker.enrollment import SpeakerEnrollment
from intents.enroll_speaker import can_handle as can_enroll_speaker
from intents.enroll_speaker import extract_name

# ---------------- Configuration ----------------

SAMPLE_RATE = 16000
CHANNELS = 1

OW_FRAME_MS = 80
OW_FRAME_SIZE = int(SAMPLE_RATE * OW_FRAME_MS / 1000)  # 1280 samples

WHISPER_MODEL = "tiny.en"

WAKE_CONFIDENCE = 0.75
WAKE_COOLDOWN = 2

COMMAND_TIMEOUT = 2.0
CONVERSATION_TIMEOUT = 5

# ---------------- Globals ----------------

audio_queue = queue.Queue()

wake_latched = False
wake_active = False
awaiting_command = False
conversation_active = False
conversation_context = {}

last_wake_time = 0
last_interaction_time = 0
tts_active = False

VAD_THRESHOLD = 0.15  # calibrated at startup

# ---------------- Models ----------------

whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

openwakeword.utils.download_models()

_WAKE_WORD_ONNX = os.path.join(os.path.dirname(__file__), "assets", "Hey_Noodle.onnx")
_wake_word_env = os.environ.get("NUDLE_WAKE_WORD")
if _wake_word_env:
    WAKE_WORD_MODEL = [_wake_word_env]
elif os.path.exists(_WAKE_WORD_ONNX):
    WAKE_WORD_MODEL = [_WAKE_WORD_ONNX]
else:
    WAKE_WORD_MODEL = ["hey jarvis"]
print(f"Wake word model: {WAKE_WORD_MODEL}")

ow_model = Model(
    wakeword_models=WAKE_WORD_MODEL,
    enable_speex_noise_suppression=False,
    vad_threshold=0.6,
    inference_framework="onnx",
)
print(f"Loaded models: {ow_model.models.keys()}")

speaker_embedder = SpeakerEmbedder(device="cpu")
speaker_registry = SpeakerRegistry()
speaker_verifier = SpeakerVerifier(speaker_registry, threshold=0.70, auto_learn_threshold=0.80)

# ---------------- Audio callback ----------------

def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(indata[:, 0].copy())

# ---------------- Helpers ----------------

def flush_audio_queue():
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

def conversation_expired():
    return time.time() - last_interaction_time > CONVERSATION_TIMEOUT

def collect_command_audio(timeout=COMMAND_TIMEOUT):
    samples = []
    start = time.time()
    while time.time() - start < timeout:
        try:
            samples.append(audio_queue.get(timeout=0.1))
        except queue.Empty:
            pass
    if not samples:
        return None
    return np.concatenate(samples).astype(np.int16).tobytes()

def collect_speech_window(duration=1.5):
    samples = []
    start = time.time()
    while time.time() - start < duration:
        try:
            samples.append(audio_queue.get(timeout=0.1))
        except queue.Empty:
            pass
    if not samples:
        return None
    return np.concatenate(samples).astype(np.int16).tobytes()

# ---------------- Voice Activity Detection ----------------

def detect_speech_segments(audio, sample_rate=16000, frame_length=0.025, frame_step=0.010):
    """
    Detect speech segments in audio using energy-based VAD.
    Returns: (has_speech, speech_ratio, clean_audio)
    """
    # Convert to float
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0

    # Calculate frame parameters
    frame_length_samples = int(frame_length * sample_rate)
    frame_step_samples = int(frame_step * sample_rate)

    # Calculate energy per frame
    frames = []
    for i in range(0, len(audio) - frame_length_samples, frame_step_samples):
        frame = audio[i:i + frame_length_samples]
        energy = np.sqrt(np.mean(frame ** 2))
        frames.append(energy)

    if not frames:
        return False, 0.0, audio

    frames = np.array(frames)

    # Adaptive threshold: mean + 0.5 * std
    threshold = np.mean(frames) + 0.5 * np.std(frames)

    # Count speech frames
    speech_frames = np.sum(frames > threshold)
    speech_ratio = speech_frames / len(frames)

    has_speech = speech_ratio > VAD_THRESHOLD

    return has_speech, speech_ratio, audio

def extract_speech_features(pcm_bytes, sample_rate=16000):
    """
    Extract quality metrics from audio for debugging.
    """
    audio = np.frombuffer(pcm_bytes, np.int16).astype(np.float32) / 32768.0

    # Energy
    energy = np.sqrt(np.mean(audio ** 2))

    # Zero-crossing rate (indicator of speech vs noise)
    zcr = np.mean(np.abs(np.diff(np.sign(audio)))) / 2

    # Peak amplitude
    peak = np.max(np.abs(audio))

    # Speech detection
    has_speech, speech_ratio, _ = detect_speech_segments(audio, sample_rate)

    return {
        "energy": energy,
        "zcr": zcr,
        "peak": peak,
        "has_speech": has_speech,
        "speech_ratio": speech_ratio,
        "duration": len(audio) / sample_rate
    }

def embed_from_pcm(pcm_bytes, debug=False):
    """
    Enhanced version with quality checks and preprocessing.
    """
    audio = np.frombuffer(pcm_bytes, np.int16).astype(np.float32) / 32768.0

    # Quality checks
    features = extract_speech_features(pcm_bytes, SAMPLE_RATE)

    if debug:
        print(f"   📊 Audio: energy={features['energy']:.4f}, "
              f"speech={features['speech_ratio']:.0%}, "
              f"duration={features['duration']:.1f}s")

    # Reject low-quality audio
    if not features["has_speech"]:
        if debug:
            print(f"   ⚠️ No speech detected")
        return None, features

    if features["energy"] < 0.005: # Energy Threshold
        if debug:
            print(f"   ⚠️ Audio too quiet")
        return None, features

    # Apply pre-emphasis filter to boost high frequencies
    audio = signal.lfilter([1, -0.97], [1], audio)

    # Normalize audio
    audio = audio / (np.max(np.abs(audio)) + 1e-6)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        sf.write(f.name, audio, SAMPLE_RATE)
        embedding = speaker_embedder.embed(f.name, debug=debug)

    return embedding, features

# ---------------- ONNX preprocessing ----------------

def preprocess_onnx_frame(frame, sample_rate=SAMPLE_RATE):
    audio = frame.astype(np.float32) / 32768.0
    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=sample_rate,
        n_fft=512,
        hop_length=160,
        n_mels=16
    )
    mel = np.log(np.maximum(mel, 1e-6))
    if mel.shape[1] < 96:
        mel = np.pad(mel, ((0,0),(0, 96 - mel.shape[1])), mode='constant')
    elif mel.shape[1] > 96:
        mel = mel[:, :96]
    return mel[np.newaxis, :, :]

# ---------------- STT ----------------

def transcribe(pcm_bytes):
    audio = np.frombuffer(pcm_bytes, np.int16).astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(audio, language="en")
    return " ".join(seg.text.strip() for seg in segments).lower()

# ---------------- Intent router ----------------

def handle_command(text):
    for module in [time_intent, radio, music, weather, gag]:
        if module.can_handle(text):
            return module.handle(text)
    return "Sorry, I didn't understand that."

def handle_followup(text, context):
    intent_name = context.get("intent")
    if intent_name in ("timer", "alarm"):
        return time_intent.handle_followup(text, context)
    return "Sorry, I didn't understand."

# ---------------- Enhanced Enrollment ----------------

def enroll_speaker_safe(name, enrollment):
    """
    Safe enrollment with quality validation.
    """
    name = name.lower()
    embeddings = []

    print(f"🎤 Starting enrollment for {name}")
    print(f"   Speak clearly and naturally")
    print(f"   Tip: Speak full sentences, not just sounds")

    successful_samples = 0
    attempts = 0
    max_attempts = 8
    target_samples = 5

    while successful_samples < target_samples and attempts < max_attempts:
        attempts += 1
        print(f"\n📝 Sample {successful_samples+1}/{target_samples} - Get ready...")
        time.sleep(1.5)

        pcm = enrollment.collect_speech(4.0)
        if not pcm:
            print("⚠️ No audio captured")
            continue

        # Quality check
        embedding, features = embed_from_pcm(pcm, debug=True)

        if embedding is None:
            print("⚠️ Audio quality too poor, try again")
            continue

        # Check consistency with existing samples
        if embeddings:
            similarities = [np.dot(embedding, prev_emb) for prev_emb in embeddings]
            avg_sim = np.mean(similarities)

            if avg_sim < 0.4:
                print(f"⚠️ Sample inconsistent (similarity={avg_sim:.2f})")
                print(f"   Make sure it's the same person speaking")
                continue

            print(f"✅ Good sample (similarity: {avg_sim:.2f})")
        else:
            print(f"✅ Baseline sample")

        embeddings.append(embedding)
        enrollment.registry.add_embedding(name, embedding)
        successful_samples += 1

    if successful_samples < 3:
        print(f"❌ Enrollment failed - only {successful_samples} good samples")
        return None

    print(f"\n🧠 Enrollment complete with {successful_samples} samples")

    # Calculate stats
    if len(embeddings) > 1:
        sims = []
        for i in range(len(embeddings)):
            for j in range(i+1, len(embeddings)):
                sim = np.dot(embeddings[i], embeddings[j])
                sims.append(sim)
        avg_intra_sim = np.mean(sims)
        print(f"   Intra-speaker similarity: {avg_intra_sim:.3f}")

        if avg_intra_sim < 0.6:
            print(f"   ⚠️ Warning: Low consistency. Consider re-enrolling.")
        elif avg_intra_sim < 0.75:
            print(f"   ⚙️ Acceptable enrollment")
        else:
            print(f"   ✅ Excellent enrollment!")

    return name

# ---------------- VAD calibration ----------------

def calibrate_vad(device, duration=2.0, margin=0.10):
    global VAD_THRESHOLD
    print(f"🔇 Calibrating VAD — stay quiet for {duration:.0f} seconds...")
    samples = []
    with sd.InputStream(
        device=device,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=OW_FRAME_SIZE,
    ) as stream:
        end = time.time() + duration
        while time.time() < end:
            chunk, _ = stream.read(OW_FRAME_SIZE)
            samples.append(chunk[:, 0].copy())

    audio = np.concatenate(samples).astype(np.float32) / 32768.0
    _, ambient_ratio, _ = detect_speech_segments(audio, SAMPLE_RATE)
    VAD_THRESHOLD = round(ambient_ratio + margin, 3)
    print(f"✅ VAD threshold set to {VAD_THRESHOLD:.3f} (ambient={ambient_ratio:.3f} + margin={margin})")

# ---------------- Main loop ----------------

def main():
    global wake_active, awaiting_command, wake_latched
    global conversation_active, conversation_context
    global last_interaction_time, last_wake_time
    global tts_active

    print("🎙️ Nüdle listening (openWakeWord ONNX)")

    # ---------------- Audio device detection ----------------
    input_device = None

    # Manual override via env var: NUDLE_INPUT_DEVICE=6
    env_device = os.environ.get("NUDLE_INPUT_DEVICE")
    if env_device is not None:
        input_device = int(env_device)
        print(f"🎤 Using device #{input_device} (NUDLE_INPUT_DEVICE override)")
    else:
        input_devices = [(i, dev) for i, dev in enumerate(sd.query_devices()) if dev["max_input_channels"] > 0]
        for i, dev in input_devices:
            print(f"  Input #{i}: {dev['name']}")

        # Priority 1: WM8960 HAT (Raspberry Pi target hardware)
        for i, dev in input_devices:
            if "wm8960" in dev["name"].lower():
                input_device = i
                print(f"🎤 Selected WM8960 HAT (#{i})")
                break

        # Priority 2: PipeWire default (None) — handles rate conversion automatically
        if input_device is None:
            try:
                sd.check_input_settings(device=None, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16")
                print("🎤 Using PipeWire default input")
            except Exception:
                # Priority 3: First numbered device that accepts 16 kHz directly
                for i, dev in input_devices:
                    try:
                        sd.check_input_settings(device=i, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16")
                        input_device = i
                        print(f"🎤 Selected #{i}: {dev['name']}")
                        break
                    except Exception:
                        continue

                if input_device is None:
                    print("⚠️ No device found supporting 16 kHz — set NUDLE_INPUT_DEVICE=<n> to pick one manually")

    calibrate_vad(input_device)

    with sd.InputStream(
        device=input_device,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        callback=audio_callback,
        blocksize=OW_FRAME_SIZE,
        latency="high",
    ):
        buffer = np.zeros(0, dtype=np.int16)

        while True:
            try:
                chunk = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            buffer = np.concatenate([buffer, chunk])

            while len(buffer) >= OW_FRAME_SIZE:
                frame = buffer[:OW_FRAME_SIZE]
                buffer = buffer[OW_FRAME_SIZE:]

                if tts_active or conversation_active:
                    continue

                # ---------------- Wake word detection ----------------
                try:
                    if getattr(ow_model, "inference_framework", None) == "onnx":
                        frame_input = preprocess_onnx_frame(frame)
                    else:
                        frame_input = frame
                    prediction = ow_model.predict(frame_input)
                except Exception as e:
                    print(f"⚠️ Wake word predict failed: {e}")
                    prediction = {}

                score = max(prediction.values(), default=0.0)
                now = time.time()
                if not wake_latched and score >= WAKE_CONFIDENCE and (now - last_wake_time) > WAKE_COOLDOWN:
                    print(f"👂 Wake word detected! (score={score:.2f})")
                    last_wake_time = now
                    wake_latched = True
                    wake_active = True
                    awaiting_command = True
                    flush_audio_queue()
                    duck()

            # ---------------- Await command ----------------
            if awaiting_command:
                awaiting_command = False
                wake_active = False

                # Collect command audio
                pcm = collect_command_audio()
                if not pcm:
                    wake_latched = False
                    unduck()
                    continue

                # Extract embedding with quality checks
                embedding, features = embed_from_pcm(pcm, debug=True)

                if embedding is None:
                    print("⚠️ Poor audio quality, skipping speaker verification")
                    speaker_name, speaker_score = None, 0.0
                else:
                    speaker_name, speaker_score = speaker_verifier.verify(embedding, auto_learn=True)

                conversation_context["speaker"] = speaker_name
                conversation_context["speaker_confidence"] = speaker_score

                # Transcribe
                text = transcribe(pcm)
                if not text:
                    wake_latched = False
                    unduck()
                    continue

                print(f"🗣️ Heard: {text}")

                # Greet if confident
                if speaker_name and speaker_score >= 0.70:
                    tts_active = True
                    speak(f"Hi {speaker_name}")
                    tts_active = False
                    print(f"✅ Recognized: {speaker_name} ({speaker_score:.2f})")
                elif speaker_name and speaker_score >= 0.50:
                    print(f"🤔 Possible speaker: {speaker_name} (confidence: {speaker_score:.2f})")
                else:
                    print(f"❓ Unknown speaker (best: {speaker_name}, {speaker_score:.2f})")

                # ---------------- Enrollment ----------------
                if can_enroll_speaker(text):
                    name = extract_name(text)

                    # Clear existing
                    if speaker_registry.has_speaker(name):
                        speaker_registry.clear_speaker(name)
                        print(f"🔄 Clearing old enrollment for {name}")

                    tts_active = True
                    speak(f"Hi {name}, let's get to know your voice. I'll ask you to speak 5 times.")
                    tts_active = False

                    time.sleep(1.0)

                    # Use enhanced enrollment
                    enrollment_obj = SpeakerEnrollment(
                        speaker_embedder,
                        speaker_registry,
                        collect_speech_window,
                        SAMPLE_RATE
                    )
                    result = enroll_speaker_safe(name, enrollment_obj)

                    if result:
                        # Immediate test
                        tts_active = True
                        speak("Great! Now say something to test if I recognize you.")
                        tts_active = False

                        time.sleep(0.5)
                        pcm_test = collect_speech_window(3.0)
                        test_embedding, test_features = embed_from_pcm(pcm_test, debug=True)

                        if test_embedding is not None:
                            test_name, test_score = speaker_verifier.verify(test_embedding, auto_learn=False)
                            print(f"🧪 Verification: {test_name} ({test_score:.3f})")

                            if test_score >= 0.70:
                                tts_active = True
                                speak(f"Perfect! I recognize you, {name}.")
                                tts_active = False
                            else:
                                tts_active = True
                                speak("I'm having trouble recognizing you. Let's try enrolling again.")
                                tts_active = False

                        stats = speaker_registry.get_stats(name)
                        print(f"📊 Final stats: {stats}")
                    else:
                        tts_active = True
                        speak("Sorry, I couldn't complete the enrollment. Let's try again later.")
                        tts_active = False

                    last_wake_time = time.time()
                    wake_latched = False
                    unduck()
                    continue

                # ---------------- Normal command routing ----------------
                response = handle_command(text)
                tts_active = True
                flush_audio_queue()
                if isinstance(response, dict):
                    conversation_active = True
                    conversation_context = response
                    last_interaction_time = time.time()
                    speak(response["prompt"])
                else:
                    speak(response)
                flush_audio_queue()
                tts_active = False
                last_wake_time = time.time()
                unduck()
                wake_latched = False

            # ---------------- Conversation follow-up ----------------
            if conversation_active:
                if conversation_expired():
                    tts_active = True
                    flush_audio_queue()
                    speak("Okay, let me know if you need anything.")
                    flush_audio_queue()
                    tts_active = False
                    last_wake_time = time.time()
                    conversation_active = False
                    conversation_context = {}
                    unduck()
                    wake_latched = False
                    continue

                pcm = collect_command_audio()
                if not pcm:
                    continue

                text = transcribe(pcm)
                print(f"🗣️ Heard: {text}")

                response = handle_followup(text, conversation_context)
                tts_active = True
                flush_audio_queue()
                if isinstance(response, dict):
                    conversation_context = response
                    speak(response["prompt"])
                else:
                    speak(response)
                    conversation_active = False
                    conversation_context = {}
                    unduck()
                    wake_latched = False
                flush_audio_queue()
                tts_active = False
                last_wake_time = time.time()

# ---------------- Entry point ----------------

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Exiting Nüdle")
