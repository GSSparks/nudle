import os
import requests
import re
from tts import speak

DEFAULT_LOCATION = os.environ.get("NUDLE_WEATHER_LOCATION", "New York City, NY")
WTTR_BASE = "https://wttr.in"

def can_handle(text: str) -> bool:
    """Return True if this text looks like a music command."""
    return any(k in text for k in ["weather", "temperature"])

def _detect_timeframe(text: str) -> str:
    if "tomorrow" in text:
        return "tomorrow"
    if "today" in text:
        return "today"
    return "outside"

def _fetch_weather(timeframe: str, location: str) -> str:
    """
    Always USCS units, speech-friendly format.
    """
    # Explicit units: u=m gives Fahrenheit/mph
    if timeframe == "tomorrow":
        fmt = "%C%t%w"
        url = f"{WTTR_BASE}/{location}?u&format={fmt}&day=1"
    else:
        fmt = "%C%t"
        url = f"{WTTR_BASE}/{location}?u&format={fmt}"

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.text.strip()

def _clean_for_speech(text: str) -> str:
    """
    Make wttr.in output sound good when spoken.
    """
    text = text.lower()
    text = text.replace("°f", " degrees fahrenheit")
    text = text.replace("mph", " miles per hour winds")
    text = text.replace(",", " and ")
    text = text.replace("+", "")
    text = text.replace("-", " negative ")
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    return text.strip()

def handle(text: str) -> str:
    """
    Returns weather string for main.py to speak.
    """
    timeframe = _detect_timeframe(text)
    try:
        raw = _fetch_weather(timeframe, DEFAULT_LOCATION)
        weather = _clean_for_speech(raw)

        if timeframe == "tomorrow":
            return f"Tomorrow's weather will be {weather}."
        elif timeframe == "today":
            return f"Today's weather is {weather}."
        else:
            return f"The weather outside is {weather}."
    except Exception as e:
        print(f"Weather error: {e}")
        return "Sorry, I couldn't get the weather right now."
