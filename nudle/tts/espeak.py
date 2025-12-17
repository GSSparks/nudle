# tts/espeak.py
import subprocess

def speak(text: str):
    subprocess.run(
        ["espeak", "-s", "165", "-v", "en-us", text],
        check=False
    )
