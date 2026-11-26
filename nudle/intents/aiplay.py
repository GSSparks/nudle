import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from speaker.preferences import prefs

_OLLAMA_URL = os.environ.get("NUDLE_OLLAMA_URL", "http://192.168.1.189:11434").rstrip("/")
_MODEL = os.environ.get("NUDLE_LLM_MODEL", "qwen3.5:4b")
_NUM_TRACKS = int(os.environ.get("NUDLE_AIPLAY_TRACKS", "5"))

player_process: subprocess.Popen | None = None
_stop_event = threading.Event()
_player_thread: threading.Thread | None = None
_speak_fn = None
_active_speaker: str | None = None

_PLAYLIST_PROMPT = (
    "Return ONLY a JSON object with one key 'playlist' containing a list of {n} songs "
    "that fit this description: '{prompt}'{context}. "
    "Each entry must be a string formatted exactly as 'Song Title - Artist Name'. "
    "No explanation, no markdown, no extra keys. Only the JSON object."
)

_MOOD_WORDS = {
    "relaxing", "relaxed", "chill", "chilled", "chilling", "calm", "calming",
    "upbeat", "energetic", "mellow", "ambient", "focused", "studying", "workout",
    "happy", "sad", "melancholy", "romantic", "evening", "morning", "late night",
    "coding", "working", "sleeping", "meditation", "party", "road trip",
    "jazz", "classical", "lofi", "lo-fi", "indie", "folk", "electronic", "acoustic",
    "christmas", "holiday", "halloween", "summer", "winter", "spring", "autumn",
    "80s", "90s", "70s", "60s", "retro", "vintage", "modern", "oldies",
    "rock", "pop", "blues", "country", "soul", "funk", "reggae", "metal", "punk",
}


def set_speak_fn(fn):
    global _speak_fn
    _speak_fn = fn


def set_speaker(name: str | None):
    global _active_speaker
    _active_speaker = name


def can_handle(text: str) -> bool:
    t = text.lower()

    # stop/skip only if our player is running
    if player_process and player_process.poll() is None:
        if any(k in t for k in ["stop", "pause", "skip", "next song"]):
            return True

    has_play = bool(re.search(r"\b(play|put on|queue|give me|find me|i want to hear|i want to listen)\b", t))
    has_vague = bool(re.search(r"\b(me some|me something|something|some music for|music for|a playlist|some\b)\b", t))
    has_mood = any(word in t for word in _MOOD_WORDS)
    has_specific_artist = bool(re.search(r"\bby\b", t))

    return has_play and (has_vague or has_mood) and not has_specific_artist


def _ask_ollama(prompt: str) -> list[str]:
    history = prefs.music_context(_active_speaker)
    if history:
        context = f". This listener has previously enjoyed: {', '.join(history)}"
    else:
        context = ""
    content = _PLAYLIST_PROMPT.format(n=_NUM_TRACKS, prompt=prompt, context=context)
    try:
        resp = requests.post(
            f"{_OLLAMA_URL}/api/chat",
            json={
                "model": _MODEL,
                "stream": False,
                "think": False,
                "messages": [{"role": "user", "content": content}],
            },
            timeout=45,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw).get("playlist", [])
    except Exception as e:
        print(f"⚠️ aiplay Ollama error: {e}")
        return []


def _search_youtube(song: str) -> tuple[str, str | None]:
    try:
        result = subprocess.run(
            ["yt-dlp", "-f", "bestaudio", f"ytsearch1:{song}",
             "--get-url", "--quiet", "--no-playlist"],
            capture_output=True, text=True, timeout=30,
        )
        url = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return song, url
    except Exception as e:
        print(f"⚠️ yt-dlp '{song}': {e}")
        return song, None


def _build_and_play(prompt: str):
    global player_process
    _stop_event.clear()

    songs = _ask_ollama(prompt)
    if not songs:
        if _speak_fn:
            _speak_fn("Sorry, I couldn't generate a playlist right now.")
        return

    print(f"🎵 AI playlist: {songs}")

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_search_youtube, s): s for s in songs}
        for future in as_completed(futures):
            song, url = future.result()
            if url:
                results[song] = url
                print(f"   ✅ {song}")
            else:
                print(f"   ❌ Not found: {song}")

    # Preserve LLM ordering
    urls = [results[s] for s in songs if s in results]

    if not urls:
        if _speak_fn:
            _speak_fn("I couldn't find any of those songs on YouTube.")
        return

    if _speak_fn:
        _speak_fn(f"Playing {len(urls)} tracks.")

    player_process = subprocess.Popen(
        ["mpv", "--no-video", "--really-quiet"] + urls,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    player_process.wait()
    completed = player_process.returncode == 0
    player_process = None

    # Weight 2 for a full listen, 1 for a stop or skip
    prefs.record_music(_active_speaker, prompt, completed=completed)
    print(f"{'✅' if completed else '⏭️'} Playlist {'completed' if completed else 'stopped'} — recorded (weight={'2' if completed else '1'})")


def stop_playback():
    global player_process
    _stop_event.set()
    if player_process and player_process.poll() is None:
        player_process.terminate()
        player_process = None


def handle(text: str) -> str:
    global _player_thread
    t = text.lower()

    if any(k in t for k in ["stop", "pause"]):
        stop_playback()
        return "Stopped."

    if any(k in t for k in ["skip", "next"]):
        if player_process and player_process.poll() is None:
            player_process.terminate()
        return "Skipping."

    stop_playback()
    from intents import music as _music
    from intents import radio as _radio
    _music.stop_current_playback()
    _radio.stop_radio()

    _player_thread = threading.Thread(target=_build_and_play, args=(text,), daemon=True)
    _player_thread.start()
    return "Let me find some music for you."
