#!/usr/bin/env python3
import queue
import threading
import sounddevice as sd
import numpy as np
import webrtcvad
from faster_whisper import WhisperModel
import time  # stdlib time

# --- Local imports ---
from tts import speak
from audio.ducking import duck, unduck
from intents import radio
from intents import music
from intents import weather
from intents import gag
from intents import time as time_intent  # ✅ aliased intent module
# from intents import status

# ---------------- Configuration ----------------

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION_MS = 20
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)

WAKE_WORDS = [
    "hey computer",
    "hey, computer",
    "a computer",
    "noodle",
    "hey noodle",
    "hey, noodle",
]

VAD_MODE = 2  # 0–3 (higher = more aggressive)
WHISPER_MODEL = "tiny.en"

# ---------------- Globals ----------------

audio_queue = queue.Queue()
vad = webrtcvad.Vad(VAD_MODE)

whisper = WhisperModel(
    WHISPER_MODEL,
    device="cpu",
    compute_type="int8"
)

wake_active = False
awaiting_command = False

conversation_active = False
conversation_context = {}
conversation_timeout = 10
last_interaction_time = 0

# ---------------- Audio callback ----------------

def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(indata.copy())

# ---------------- VAD helpers ----------------

def frame_generator():
    """Yield 20ms PCM frames"""
    buffer = b""

    while True:
        data = audio_queue.get()
        pcm = (data[:, 0] * 32768).astype(np.int16).tobytes()
        buffer += pcm

        while len(buffer) >= FRAME_SIZE * 2:
            yield buffer[: FRAME_SIZE * 2]
            buffer = buffer[FRAME_SIZE * 2 :]

def collect_utterance():
    """Collect speech until silence detected"""
    voiced_frames = []
    silence_frames = 0
    max_silence = int(0.5 / (FRAME_DURATION_MS / 1000))

    for frame in frame_generator():
        if vad.is_speech(frame, SAMPLE_RATE):
            voiced_frames.append(frame)
            silence_frames = 0
        else:
            silence_frames += 1
            if voiced_frames and silence_frames > max_silence:
                break

    if not voiced_frames:
        return None

    return b"".join(voiced_frames)

def conversation_expired():
    return time.time() - last_interaction_time > conversation_timeout

# ---------------- STT ----------------

def transcribe(pcm_bytes):
    audio = np.frombuffer(pcm_bytes, np.int16).astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(audio, language="en")
    return " ".join(seg.text.strip() for seg in segments).lower()

# ---------------- Intent router ----------------

def handle_command(text):
    if radio.can_handle(text):
        return radio.handle(text)

    if music.can_handle(text):
        return music.handle(text)

    if weather.can_handle(text):
        return weather.handle(text)

    if time_intent.can_handle(text):
        return time_intent.handle(text)

    if gag.can_handle(text):
        return gag.handle(text)

    return "Sorry, I didn’t understand that."

def handle_followup(text, context):
    intent_name = context.get("intent")

    if intent_name in ("timer", "alarm"):
        return time_intent.handle_followup(text, context)

    return "Sorry, I didn’t understand."

# ---------------- Main loop ----------------

def main():
    global wake_active
    global awaiting_command
    global conversation_active
    global conversation_context
    global last_interaction_time

    print("🎙️ reson-voice listening (VAD + wake word)")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=audio_callback,
    ):
        while True:
            pcm = collect_utterance()
            if not pcm:
                continue

            text = transcribe(pcm)
            if not text:
                continue

            print(f"🗣️ Heard: {text}")

            # ---------------- IDLE ----------------
            if not wake_active and not conversation_active:
                for ww in WAKE_WORDS:
                    if ww in text:
                        wake_active = True
                        awaiting_command = True
                        print(f"👂 Wake word detected: {ww}")
                        duck()
                        break
                continue

            # ---------------- IN CONVERSATION ----------------
            if conversation_active:
                if conversation_expired():
                    speak("Okay, let me know if you need anything.")
                    conversation_active = False
                    conversation_context = {}
                    unduck()
                    continue

                last_interaction_time = time.time()
                response = handle_followup(text, conversation_context)

                if isinstance(response, dict):
                    conversation_context = response
                    speak(response["prompt"])
                    continue

                speak(response)
                conversation_active = False
                conversation_context = {}
                unduck()
                continue

            # ---------------- AWAIT COMMAND ----------------
            if awaiting_command:
                awaiting_command = False
                wake_active = False

                response = handle_command(text)

                if isinstance(response, dict):
                    conversation_active = True
                    conversation_context = response
                    last_interaction_time = time.time()
                    speak(response["prompt"])
                    continue

                speak(response)
                unduck()

# ---------------- Entry point ----------------

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Exiting reson-voice")
