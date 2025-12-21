#!/usr/bin/env python3
import queue
import sounddevice as sd
import numpy as np
import time
import tempfile
import soundfile as sf
import librosa

from faster_whisper import WhisperModel

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

WAKE_CONFIDENCE = 0.9
WAKE_COOLDOWN = 20

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

# ---------------- Models ----------------

whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

openwakeword.utils.download_models()

ow_model = Model(
    wakeword_models=["hey jarvis"],  # ONNX model
    enable_speex_noise_suppression=False,
    vad_threshold=0.6,
    #inference_framework="onnx",
)

speaker_embedder = SpeakerEmbedder(device="cpu")
speaker_registry = SpeakerRegistry()
speaker_verifier = SpeakerVerifier(speaker_registry, threshold=0.75)

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

def embed_from_pcm(pcm_bytes):
    audio = np.frombuffer(pcm_bytes, np.int16).astype(np.float32) / 32768.0
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        sf.write(f.name, audio, SAMPLE_RATE)
        return speaker_embedder.embed(f.name)

def debug_speaker(pcm_bytes, label=""):
    try:
        embedding = embed_from_pcm(pcm_bytes)
        name, score = speaker_verifier.verify(embedding)
        if name:
            print(f"🎤 Speaker{label}: {name} ({score:.2f})")
        else:
            print(f"🎤 Speaker{label}: unknown ({score:.2f})")
        return name, score
    except Exception as e:
        print(f"⚠️ Speaker debug failed: {e}")
        return None, 0.0

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
    return mel[np.newaxis, :, :]  # [1,16,96]

# ---------------- STT ----------------

def transcribe(pcm_bytes):
    audio = np.frombuffer(pcm_bytes, np.int16).astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(audio, language="en")
    return " ".join(seg.text.strip() for seg in segments).lower()

# ---------------- Intent router ----------------

def handle_command(text):
    for module in [radio, music, weather, time_intent, gag]:
        if module.can_handle(text):
            return module.handle(text)
    return "Sorry, I didn’t understand that."

def handle_followup(text, context):
    intent_name = context.get("intent")
    if intent_name in ("timer", "alarm"):
        return time_intent.handle_followup(text, context)
    return "Sorry, I didn’t understand."

# ---------------- Main loop ----------------

def main():
    global wake_active, awaiting_command, wake_latched
    global conversation_active, conversation_context
    global last_interaction_time, last_wake_time
    global tts_active

    print("🎙️ reson-voice listening (openWakeWord ONNX)")

    # ---------------- Audio device detection ----------------
    input_device = None
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"Input device #{i}: {dev['name']}")
            if "wm8960" in dev["name"].lower():
                input_device = i
    if input_device is None:
        print("⚠️ Waveshare WM8960 not found, using default input")

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
                pcm = collect_command_audio()
                if not pcm:
                    wake_latched = False
                    unduck()
                    continue

                speaker_pcm = collect_speech_window(1.5)
                if speaker_pcm:
                    speaker_name, speaker_score = debug_speaker(speaker_pcm, label=" (command)")
                else:
                    speaker_name, speaker_score = None, 0.0

                embedding = embed_from_pcm(pcm)
                speaker_name, speaker_score = speaker_verifier.verify(embedding)
                conversation_context["speaker"] = speaker_name
                conversation_context["speaker_confidence"] = speaker_score

                text = transcribe(pcm)
                if not text:
                    wake_latched = False
                    unduck()
                    continue

                print(f"🗣️ Heard: {text}")
                if speaker_name and speaker_score >= 0.8:
                    tts_active = True
                    speak(f"Hi {speaker_name}")
                    tts_active = False

                # ---------------- Enrollment ----------------
                if can_enroll_speaker(text):
                    name = extract_name(text)
                    tts_active = True
                    speak(f"Hi {name}, it’s nice to meet you. Please speak naturally for a moment.")
                    tts_active = False

                    enrollment = SpeakerEnrollment(speaker_embedder, speaker_registry, collect_speech_window)
                    enrollment.enroll(name, samples=4, seconds=4.0)

                    pcm_test = collect_speech_window(2.0)
                    spk, score = speaker_verifier.verify(embed_from_pcm(pcm_test))
                    print(f"🎤 Verification test: {spk} ({score:.2f})")

                    tts_active = True
                    speak(f"Thanks {name}, I’ll remember you.")
                    tts_active = False

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

# ---------------- Entry point ----------------

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Exiting Nüdle")
