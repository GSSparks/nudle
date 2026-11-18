# tts/espeak.py
import subprocess
import shutil

_ESPEAK = shutil.which("espeak") or shutil.which("espeak-ng")

def speak(text: str):
    if not _ESPEAK:
        print(f"(TTS) {text}")
        return
    subprocess.run(
        [_ESPEAK, "-s", "165", "-v", "en-us", text],
        check=False
    )
