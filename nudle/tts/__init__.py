# tts/__init__.py
import os

ENGINE = os.environ.get("RESON_TTS", "piper")

speak = None

def _load_engine():
    global speak
    if ENGINE == "piper":
        try:
            from .piper import speak as piper_speak
            # quick test to make sure Piper works
            try:
                piper_speak(" ")
                speak = piper_speak
                print("✅ Using Piper TTS engine")
                return
            except Exception as e:
                print(f"⚠️ Piper runtime test failed, falling back to espeak: {e}")
        except Exception as e:
            print(f"⚠️ Piper import failed, falling back to espeak: {e}")

    # Fallback to espeak
    try:
        from .espeak import speak as espeak_speak
        speak = espeak_speak
        print("✅ Using espeak TTS engine")
    except Exception as e:
        print(f"❌ Espeak failed to load: {e}")
        speak = lambda text: print(f"(TTS fail) {text}")

_load_engine()
