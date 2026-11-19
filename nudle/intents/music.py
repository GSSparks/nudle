# intents/music.py
import threading
import subprocess
import requests
import re
import time
import string
import difflib

# ---------------- Globals ----------------

PLAYER_CMD = ["mpv", "--quiet", "--no-video"]
BACKEND_URL = "http://localhost:8000/playlist"

tracks = []
current_index = 0
stop_event = threading.Event()
next_event = threading.Event()
player_process = None
player_thread = None

LAST_PLAY_TIME = 0
INTENT_COOLDOWN = 2

player_lock = threading.Lock()

# ---------------- Intent keywords ----------------

PLAY_KEYWORDS = ["play", "put", "hear", "listen", "start", "queue"]
STOP_KEYWORDS = ["stop", "pause", "halt", "quiet", "shut"]
SKIP_KEYWORDS = ["next", "skip", "forward"]

# Common misrecognitions
PLAY_FUZZY = {
    "place": "play",
    "pay": "play",
    "plate": "play",
    "plane": "play",
    "playing": "play",
    "played": "play",
    "plays": "play",
    "player": "play",
}

STOP_FUZZY = {
    "top": "stop",
    "shop": "stop",
    "stopped": "stop",
}

SKIP_FUZZY = {
    "skip": "skip",
    "skipping": "skip",
    "snip": "skip",
}

# ---------------- Normalize helpers ----------------

def normalize_name(s: str) -> str:
    return s.lower().translate(str.maketrans("", "", string.punctuation)).strip()

def fuzzy_match_word(word: str, keyword_list: list, threshold: float = 0.75) -> bool:
    """Check if a word matches any keyword using fuzzy matching."""
    if word in keyword_list:
        return True

    # Check for close matches
    matches = difflib.get_close_matches(word, keyword_list, n=1, cutoff=threshold)
    return len(matches) > 0

def correct_command_word(text: str) -> str:
    """Apply fuzzy corrections to common misrecognitions."""
    words = text.split()
    corrected = []

    for word in words:
        # Check play fuzzy mappings
        if word in PLAY_FUZZY:
            corrected.append(PLAY_FUZZY[word])
        elif word in STOP_FUZZY:
            corrected.append(STOP_FUZZY[word])
        elif word in SKIP_FUZZY:
            corrected.append(SKIP_FUZZY[word])
        else:
            # Check fuzzy match against all play keywords
            if fuzzy_match_word(word, PLAY_KEYWORDS, threshold=0.8):
                closest = difflib.get_close_matches(word, PLAY_KEYWORDS, n=1, cutoff=0.8)
                corrected.append(closest[0] if closest else word)
            elif fuzzy_match_word(word, STOP_KEYWORDS, threshold=0.8):
                closest = difflib.get_close_matches(word, STOP_KEYWORDS, n=1, cutoff=0.8)
                corrected.append(closest[0] if closest else word)
            elif fuzzy_match_word(word, SKIP_KEYWORDS, threshold=0.8):
                closest = difflib.get_close_matches(word, SKIP_KEYWORDS, n=1, cutoff=0.8)
                corrected.append(closest[0] if closest else word)
            else:
                corrected.append(word)

    result = " ".join(corrected)
    if result != text:
        print(f"🔧 Corrected: '{text}' → '{result}'")
    return result

# ---------------- Text cleanup ----------------

INCIDENTAL_PHRASES = [
    "i really would like to", "id really like to", "i would like to",
    "id like to", "i want to", "i wanna", "please", "could you", "can you"
]

def normalize_text(text: str) -> str:
    text = normalize_name(text)

    # Only correct if FIRST word is in explicit fuzzy dictionaries
    words = text.split()
    if words and words[0] in PLAY_FUZZY:
        words[0] = PLAY_FUZZY[words[0]]
        text = " ".join(words)
        print(f"🔧 Corrected: first word to '{words[0]}'")
    elif words and words[0] in STOP_FUZZY:
        words[0] = STOP_FUZZY[words[0]]
        text = " ".join(words)
        print(f"🔧 Corrected: first word to '{words[0]}'")
    elif words and words[0] in SKIP_FUZZY:
        words[0] = SKIP_FUZZY[words[0]]
        text = " ".join(words)
        print(f"🔧 Corrected: first word to '{words[0]}'")

    for phrase in INCIDENTAL_PHRASES:
        text = text.replace(phrase, "")
    return " ".join(text.split())

# ---------------- Slot extraction ----------------

def extract_slots(text: str) -> dict:
    slots = {"album": None, "artist": None, "genre": None, "raw": None}

    m = re.search(r"\balbum\s+([a-z0-9 ]+)", text)
    if m:
        slots["album"] = m.group(1).strip()
        return slots

    m = re.search(r"\bgenre\s+([a-z0-9 ]+)", text)
    if m:
        slots["genre"] = m.group(1).strip()
        return slots

    m = re.search(r"\bby\s+([a-z0-9 ]+)", text)
    if m:
        slots["artist"] = m.group(1).strip()

    slots["raw"] = extract_free_text(text)
    return slots

def extract_free_text(text: str) -> str:
    # Expanded list to include more filler words
    text = re.sub(
        r"\b(play|put|on|hear|listen|music|song|album|genre|the|by|from|some|a|an|start|queue)\b",
        "",
        text
    )
    return " ".join(text.split())

# ---------------- Playback control ----------------

def stop_current_playback():
    """Stop any currently playing track and wait for thread to finish."""
    global player_process, player_thread
    stop_event.set()
    next_event.set()

    with player_lock:
        if player_process and player_process.poll() is None:
            player_process.terminate()
            player_process = None

    if player_thread and player_thread.is_alive():
        player_thread.join(timeout=2.0)
        player_thread = None

    stop_event.clear()
    next_event.clear()

def skip_to_next_track():
    global player_process
    next_event.set()
    with player_lock:
        if player_process and player_process.poll() is None:
            player_process.terminate()
            player_process = None

# ---------------- Playback ----------------

def play_tracks(tracks_list):
    """
    Play a list of tracks using mpg123. Automatically handles URL prepending
    and thread-safe playback control.
    """
    global current_index, player_process, LAST_PLAY_TIME
    stop_event.clear()
    next_event.clear()
    LAST_PLAY_TIME = time.time()

    for current_index, track in enumerate(tracks_list):
        if stop_event.is_set():
            break

        # Get URL and ensure it's fully qualified
        url = track.get("url")
        if isinstance(url, list):
            url = url[0]
        if not isinstance(url, str):
            print(f"⚠️ Invalid URL for track: {track}")
            continue

        # Prepend backend host if URL is relative
        if url.startswith("/local"):
            url = f"http://localhost:8000{url}"

        # Escape any spaces or special chars for mpg123
        url = url.replace(" ", "%20")

        title = track.get("title", "Unknown")
        print(f"🎵 Now playing: {title} -> {url}")
        print(url)

        try:
            with player_lock:
                player_process = subprocess.Popen(PLAYER_CMD + [url])

            while True:
                with player_lock:
                    proc = player_process

                if proc is None or proc.poll() is not None:
                    break

                if stop_event.is_set() or next_event.is_set():
                    with player_lock:
                        if player_process and player_process.poll() is None:
                            player_process.terminate()
                            player_process = None
                    next_event.clear()
                    break

                time.sleep(0.1)

        except KeyboardInterrupt:
            break

    with player_lock:
        player_process = None


# ---------------- Backend interaction ----------------

def check_playlist_exists(prompt):
    """Check if a playlist exists WITHOUT starting playback."""
    try:
        res = requests.post(
            BACKEND_URL,
            json={"prompt": prompt},
            timeout=10,
        )
        if res.status_code == 404:
            return False, None
        res.raise_for_status()
        data = res.json()
        return bool(data.get("tracks")), data
    except Exception as e:
        print(f"⚠️ Error checking playlist: {e}")
        return False, None

def fetch_playlist(prompt, interrupt=True):
    """Fetch playlist and START playback."""
    global tracks, player_thread

    try:
        res = requests.post(
            BACKEND_URL,
            json={"prompt": prompt},
            timeout=10,
        )

        if res.status_code == 404:
            return False, None
        res.raise_for_status()
        data = res.json()

        new_tracks = data.get("tracks", [])
        if not new_tracks:
            return False, data

        if interrupt:
            stop_current_playback()

        tracks = new_tracks

        player_thread = threading.Thread(target=play_tracks, args=(tracks,), daemon=True)
        player_thread.start()

        return True, data

    except Exception as e:
        print(f"⚠️ Error fetching playlist: {e}")
        return False, None

# ---------------- Suggestions ----------------

def fetch_suggestions(query: str, n: int = 3) -> list:
    try:
        res = requests.get(
            "http://localhost:8000/suggest",
            params={"q": query, "n": n},
            timeout=5,
        )
        res.raise_for_status()
        return [(s["type"], s["value"]) for s in res.json().get("suggestions", [])]
    except Exception as e:
        print(f"⚠️ Suggest failed: {e}")
        return []


def _suggestion_response(query: str) -> str | dict:
    suggestions = fetch_suggestions(query)
    if not suggestions:
        return f"Sorry, I couldn't find anything like {query}."
    parts = [f"the {ct} {cv}" for ct, cv in suggestions[:2]]
    opts = " or ".join(parts)
    return {
        "prompt": f"I couldn't find {query}, but I have {opts}. Want to hear one?",
        "intent": "music",
        "expect": "clarification",
        "candidates": suggestions,
    }

# ---------------- Music intent parser ----------------

def parse_music_prompt(prompt: str) -> dict:
    """Parse the prompt to determine intent WITHOUT starting playback."""
    text = normalize_text(prompt)
    text = re.split(r"[.?!]", text)[0].strip()
    slots = extract_slots(text)

    if slots["album"]:
        return {"type": "album", "value": slots["album"], "raw": text}
    if slots["genre"]:
        return {"type": "genre", "value": slots["genre"], "raw": text}
    if slots["artist"]:
        return {"type": "artist", "value": slots["artist"], "raw": text}

    raw = slots["raw"]
    if not raw:
        return {"type": "unknown", "value": None, "raw": text}

    # Partial album name (split on common separators before multi-match check)
    album_value = raw
    for separator in [' - ', ': ', ' / ']:
        if separator in raw:
            first_part = raw.split(separator)[0].strip()
            if first_part and check_playlist_exists(f"album:{first_part}")[0]:
                album_value = first_part
                break

    # Collect all matching types
    candidates = []
    if check_playlist_exists(f"album:{album_value}")[0]:
        candidates.append(("album", album_value))
    if check_playlist_exists(f"genre:{raw}")[0]:
        candidates.append(("genre", raw))
    if check_playlist_exists(f"artist:{raw}")[0]:
        candidates.append(("artist", raw))
    if check_playlist_exists(raw)[0]:
        candidates.append(("song", raw))

    if not candidates:
        return {"type": "unknown", "value": raw, "raw": text}
    if len(candidates) == 1:
        t, v = candidates[0]
        return {"type": t, "value": v, "raw": text}
    return {"type": "ambiguous", "candidates": candidates, "value": raw, "raw": text}

# ---------------- Intent interface ----------------

def can_handle(text: str) -> bool:
    """Enhanced intent detection with fuzzy matching."""
    text = text.lower()
    words = text.split()

    # Direct keyword match
    for word in words:
        if word in PLAY_KEYWORDS + STOP_KEYWORDS + SKIP_KEYWORDS:
            return True
        if word in PLAY_FUZZY or word in STOP_FUZZY or word in SKIP_FUZZY:
            return True
        # Fuzzy match
        if (fuzzy_match_word(word, PLAY_KEYWORDS, 0.75) or
            fuzzy_match_word(word, STOP_KEYWORDS, 0.75) or
            fuzzy_match_word(word, SKIP_KEYWORDS, 0.75)):
            return True

    # Fallback to general music keywords
    return any(k in text for k in ["music", "song", "album"])

def handle(text: str):
    global LAST_PLAY_TIME
    now = time.time()
    if now - LAST_PLAY_TIME < INTENT_COOLDOWN:
        return None

    text = normalize_text(text)
    text = re.split(r"[.?!]", text)[0].strip()

    # Check for stop/pause commands
    words = text.split()
    for word in words:
        if word in STOP_KEYWORDS or word in STOP_FUZZY or fuzzy_match_word(word, STOP_KEYWORDS, 0.75):
            stop_current_playback()
            return "Music stopped."

    # Check for skip commands
    for word in words:
        if word in SKIP_KEYWORDS or word in SKIP_FUZZY or fuzzy_match_word(word, SKIP_KEYWORDS, 0.75):
            skip_to_next_track()
            return "Skipping to the next track."

    intent = parse_music_prompt(text)
    print("🎯 MUSIC INTENT:", intent)

    t = intent["type"]
    v = intent.get("value")

    if t in ["album", "artist", "genre", "song"]:
        tag = f"{t}:{v}" if t in ["album", "artist", "genre"] else v
        success, returned_data = fetch_playlist(tag, interrupt=True)
        if success and returned_data:
            matched_value = returned_data.get("matched", {}).get("value", v)
            if t == "album":
                return f"Playing the album {matched_value}"
            elif t == "artist":
                return f"Playing music by {matched_value}"
            elif t == "genre":
                return f"Playing some {matched_value} music"
            else:
                return f"Playing {matched_value}"
        else:
            return _suggestion_response(v)

    if t == "ambiguous":
        candidates = intent["candidates"]
        parts = [f"the {ct} {cv}" for ct, cv in candidates[:3]]
        opts = " or ".join(parts) if len(parts) == 2 else ", ".join(parts[:-1]) + f", or {parts[-1]}"
        return {
            "prompt": f"Did you mean {opts}?",
            "intent": "music",
            "expect": "clarification",
            "candidates": candidates,
        }

    # Has a value but nothing matched — suggest alternatives
    if v:
        return _suggestion_response(v)

    # No target at all — shuffle the whole library
    success, _ = fetch_playlist("random", interrupt=True)
    if success:
        return "Playing some music."
    return "Sorry, I couldn't find any music."


def handle_followup(text: str, context: dict) -> str:
    candidates = context.get("candidates", [])
    text_norm = normalize_text(text)

    # Match by type keyword ("album", "artist", "genre", "song")
    for ct, cv in candidates:
        if ct in text_norm:
            tag = f"{ct}:{cv}" if ct in ["album", "artist", "genre"] else cv
            success, data = fetch_playlist(tag, interrupt=True)
            if success:
                matched = data.get("matched", {}).get("value", cv)
                return f"Playing {ct} {matched}."

    # Match by value name (whole-word only to avoid "blue" matching "bluegrass")
    words = set(text_norm.split())
    for ct, cv in candidates:
        cv_words = set(cv.split())
        if cv_words & words or difflib.get_close_matches(text_norm, [cv], n=1, cutoff=0.7):
            tag = f"{ct}:{cv}" if ct in ["album", "artist", "genre"] else cv
            success, data = fetch_playlist(tag, interrupt=True)
            if success:
                matched = data.get("matched", {}).get("value", cv)
                return f"Playing {ct} {matched}."

    parts = [f"the {ct}" for ct, _ in candidates]
    return f"Sorry, I didn't catch that. Try saying {' or '.join(parts)}."
