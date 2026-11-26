import json
import os
import requests

_OLLAMA_URL = os.environ.get("NUDLE_OLLAMA_URL", "http://192.168.1.189:11434").rstrip("/")
_MODEL = os.environ.get("NUDLE_LLM_MODEL", "qwen3.5:4b")

_SYSTEM = (
    "You are Nüdle, a voice assistant. "
    "If the user's request is about one of these things, respond with ONLY a JSON object — no other text.\n"
    "Examples:\n"
    '  "turn off the bedroom lights"   -> {"route":"lights","text":"turn off the bedroom lights"}\n'
    '  "switch the side lamps off"     -> {"route":"lights","text":"turn off the side lamps"}\n'
    '  "dim the living room"           -> {"route":"lights","text":"dim the living room lights"}\n'
    '  "play ray of light by madonna"  -> {"route":"music","text":"play ray of light by madonna"}\n'
    '  "play some chill jazz"          -> {"route":"music","text":"play some chill jazz"}\n'
    '  "what\'s the weather today"     -> {"route":"weather","text":"what is the weather today"}\n'
    '  "set a timer for 10 minutes"    -> {"route":"time","text":"set a timer for 10 minutes"}\n'
    '  "play kexp radio"               -> {"route":"radio","text":"play kexp"}\n'
    "If none of those match, answer in 1-2 spoken sentences with no markdown."
)


def handle(text: str) -> str | dict:
    try:
        resp = requests.post(
            f"{_OLLAMA_URL}/api/chat",
            json={
                "model": _MODEL,
                "stream": False,
                "think": False,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": text},
                ],
            },
            timeout=45,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                if "route" in data and "text" in data:
                    return data
            except json.JSONDecodeError:
                pass
        return raw
    except requests.exceptions.ConnectionError:
        return "I can't reach my language model right now. Is Ollama running?"
    except Exception as e:
        print(f"⚠️ Ollama error: {e}")
        return "Sorry, something went wrong with my language model."
