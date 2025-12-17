# intents/music.py
import threading
import subprocess
import requests
import os
import re
import time
import string
import difflib

# ---------------- Globals ----------------
PLAYER_CMD = "mpg123"
BACKEND_URL = "http://localhost:8000/playlist"

KNOWN_GENRES = []
KNOWN_ALBUMS = []

tracks = []
current_index = 0
stop_event = threading.Event()
next_event = threading.Event()
player_process = None

LAST_PLAY_TIME = 0
INTENT_COOLDOWN = 3  # seconds

# ---------------- Normalize helpers ----------------

def normalize_name(s: str) -> str:
    return (
        s.lower()
        .translate(str.maketrans("", "", string.punctuation))
        .strip()
    )

# ---------------- Explicit Genre Detection ----------------

def detect_genre_explicit(text: str) -> str | None:
    """
    Detect genre safely without stealing song titles.
    Supports:
      - play some jazz
      - some rock
      - jazz
      - play jazz music
    """
    if not KNOWN_GENRES:
        return None

    text_norm = normalize_name(text)
    print("DEBUG genre text:", text_norm)

    # Strip leading command words + optional 'some'
    stripped = re.sub(
        r"^(play|put on)(?:\s+some)?\s+",
        "",
        text_norm
    ).strip()

    # Strip optional trailing "music"
    stripped = re.sub(r"\s+music$", "", stripped).strip()

    print("DEBUG stripped:", stripped)

    # Phrase must be short to be a genre
    if len(stripped.split()) > 3:
        return None

    # Exact match
    if stripped in KNOWN_GENRES:
        return stripped

    # Fuzzy match
    matches = difflib.get_close_matches(
        stripped,
        KNOWN_GENRES,
        n=1,
        cutoff=0.9
    )

    return matches[0] if matches else None

# ---------------- Explicit Album Detection ----------------

def detect_album_explicit(text: str) -> tuple[str, str | None] | None:
    """
    Detect album requests with optional artist.
    Returns (album, artist?) or None

    Examples:
      - play the album aja
      - play zz tops album greatest hits
      - play album greatest hits by zz top
    """
    if not KNOWN_ALBUMS:
        return None

    text = normalize_name(text)

    patterns = [
        # play zz tops album greatest hits
        r"(?:play|put on)\s+(?P<artist>[a-z0-9 ]+?)s?\s+album\s+(?P<album>[a-z0-9 ]+)$",

        # play album greatest hits by zz top
        r"(?:play|put on)\s+(?:the\s+)?album\s+(?P<album>[a-z0-9 ]+)\s+by\s+(?P<artist>[a-z0-9 ]+)$",

        # play album aja
        r"(?:play|put on)\s+(?:the\s+)?album\s+(?P<album>[a-z0-9 ]+)$",
    ]

    for p in patterns:
        m = re.match(p, text)
        if not m:
            continue

        album = m.group("album").strip()
        artist = m.groupdict().get("artist")

        album_norm = normalize_name(album)

        if album_norm in KNOWN_ALBUMS:
            return album_norm, artist

        matches = difflib.get_close_matches(
            album_norm, KNOWN_ALBUMS, n=1, cutoff=0.75
        )
        if matches:
            return matches[0], artist

    return None

# ---------------- Query extraction ----------------

def extract_song_or_artist(text: str) -> str:
    """
    Extract song / artist query.
    Never returns genre or album.
    """
    text = re.sub(r"[^\w\s]", " ", text.lower())
    text = " ".join(text.split())

    text = re.sub(
        r"\b(play|put on|please|i want|i'd like|the|song|music)\b",
        "",
        text,
    )

    return text.strip()

# ---------------- Playback control ----------------

def stop_current_playback():
    global player_process
    stop_event.set()
    next_event.set()
    if player_process and player_process.poll() is None:
        player_process.terminate()
    time.sleep(0.2)
    stop_event.clear()
    next_event.clear()

def skip_to_next_track():
    global player_process
    next_event.set()
    if player_process and player_process.poll() is None:
        player_process.terminate()

# ---------------- Playback ----------------

def play_tracks(tracks_list):
    global current_index, player_process, LAST_PLAY_TIME
    stop_event.clear()
    next_event.clear()
    LAST_PLAY_TIME = time.time()

    for current_index, track in enumerate(tracks_list):
        if stop_event.is_set():
            break

        url = track.get("url")
        title = track.get("title", "Unknown")
        print(f"🎵 Now playing: {title} ({url})")

        try:
            player_process = subprocess.Popen([PLAYER_CMD, "-q", url])
            while player_process.poll() is None:
                if stop_event.is_set() or next_event.is_set():
                    player_process.terminate()
                    next_event.clear()
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            break

    player_process = None

# ---------------- Backend interaction ----------------

def fetch_playlist(prompt):
    global tracks
    stop_current_playback()

    try:
        res = requests.post(
            BACKEND_URL,
            json={"prompt": prompt, "mode": "local", "source": "local"},
            timeout=10,
        )

        if res.status_code == 404:
            return False, None

        res.raise_for_status()
        data = res.json()
        tracks = data.get("tracks", [])

        if not tracks:
            return False, None

        threading.Thread(
            target=play_tracks,
            args=(tracks,),
            daemon=True
        ).start()

        return True, tracks

    except Exception as e:
        print(f"⚠️ Error fetching playlist: {e}")
        return False, None

# ---------------- Artist correction ----------------

def suggest_artist_variants(bad_name: str) -> list[str]:
    COMMON_FIXES = {
        "stilly dan": ["steely dan"],
        "air all smith": ["aerosmith"],
        "errol smith": ["aerosmith"],
        "corn": ["korn"],
    }

    bad = normalize_name(bad_name)
    if bad in COMMON_FIXES:
        return COMMON_FIXES[bad]

    return [bad.replace(" ", "")]

# ---------------- Intent interface ----------------

def can_handle(text: str) -> bool:
    text = text.lower()
    return any(k in text for k in ["play", "music", "song", "album", "stop", "pause", "skip", "next"])

def handle(text: str):
    global KNOWN_GENRES, KNOWN_ALBUMS

    now = time.time()
    if now - LAST_PLAY_TIME < INTENT_COOLDOWN:
        return None

    # Load genres + albums
    try:
        if not KNOWN_GENRES:
            g = requests.get("http://localhost:8000/genres", timeout=5).json()
            KNOWN_GENRES = [normalize_name(x) for x in g.get("genres", [])]
            print(f"🎼 Loaded {len(KNOWN_GENRES)} genres")

        if not KNOWN_ALBUMS:
            a = requests.get("http://localhost:8000/albums", timeout=5).json()
            KNOWN_ALBUMS = [normalize_name(x) for x in a.get("albums", [])]
            print(f"💿 Loaded {len(KNOWN_ALBUMS)} albums")

    except Exception as e:
        print(f"⚠️ Failed loading metadata: {e}")

    text = text.lower().strip()

    for w in ["hey computer", "hey, computer", "computer"]:
        text = text.replace(w, " ")

    text = re.split(r"[.?!]", text)[0].strip()

    # Stop / skip
    if any(w in text for w in ["stop", "pause", "shut up"]):
        stop_current_playback()
        return "Music stopped."

    if any(w in text for w in ["next", "skip"]):
        skip_to_next_track()
        return "Skipping to the next track."

    # 1 Album (strongest intent)
    album_data = detect_album_explicit(text)
    if album_data:
        album, artist = album_data

        query = f"album:{album}"
        if artist:
            query += f" by {artist}"

        print(f"💿 Album intent detected: album={album}, artist={artist}")

        success, _ = fetch_playlist(query)
        if success:
            return f"Playing the album {album}"
        return f"Sorry, I couldn’t find the album {album}"

    # 2 Genre
    genre = detect_genre_explicit(text)
    print("DEBUG: ", genre)
    if genre:
        query = f"genre:{genre}"
        print(f"🎼 Genre intent detected: {genre}")
        success, _ = fetch_playlist(query)
        if success:
            return f"Playing some {genre} music."
        return f"Sorry, I couldn’t find any {genre} music."

    # 3 Song / artist
    song_query = extract_song_or_artist(text)
    if song_query:
        print(f"🎶 Music intent detected: {song_query}")
        success, _ = fetch_playlist(song_query)
        if success:
            return f"Playing {song_query}"

    return "Sorry, I couldn’t find that music."
