# audio/backend.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from urllib.parse import quote, unquote
import os
import glob
import random
import string
import json
import threading
import difflib
import re
from mutagen import File as MutagenFile
from threading import Lock

# ---------------- Configuration ----------------

LOCAL_MUSIC_DIR = "/home/gsparks/server/Music"
INDEX_FILE = "/tmp/music_index.json"

# ---------------- Globals ----------------

LIB_INDEX = []
INDEX_LOCK = Lock()
INDEXING = False

# ---------------- App ----------------

app = FastAPI(title="Reson-Voice Music Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Models ----------------

class Prompt(BaseModel):
    prompt: str
    mode: str = "local"
    source: str = "local"

# ---------------- Helpers ----------------

def normalize(s: str) -> str:
    if not s:
        return ""
    s = s.lower().replace("&", " and ")
    s = s.translate(str.maketrans("", "", string.punctuation))
    return " ".join(s.split()).strip()

def snapshot_index():
    with INDEX_LOCK:
        return list(LIB_INDEX)

def save_index():
    with INDEX_LOCK:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(LIB_INDEX, f, ensure_ascii=False, indent=2)

def load_index() -> bool:
    global LIB_INDEX
    if not os.path.exists(INDEX_FILE):
        return False
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            LIB_INDEX = json.load(f)
        print(f"📀 Loaded {len(LIB_INDEX)} tracks")
        return True
    except Exception as e:
        print("❌ Index load failed:", e)
        return False

# ---------------- Metadata ----------------

def get_track_metadata(path: str) -> dict:
    title = os.path.splitext(os.path.basename(path))[0]
    artist = ""
    album = ""
    genre = ""

    try:
        m = MutagenFile(path, easy=True)
        if m:
            title = m.get("title", [title])[0]
            artist = m.get("artist", [""])[0]
            album = m.get("album", [""])[0]
            genre = m.get("genre", [""])[0]
    except Exception:
        pass

    return {
        "path": path,
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "key": f"{normalize(title)} - {normalize(artist)}".strip(" -"),
    }

def available_genres():
    return sorted({
        normalize(e["genre"])
        for e in snapshot_index()
        if e.get("genre")
    })

def available_albums():
    return sorted({
        normalize(e["album"])
        for e in snapshot_index()
        if e.get("album")
    })

# ---------------- Indexing ----------------

def background_index_library():
    global INDEXING
    if INDEXING:
        return

    INDEXING = True
    print("🎧 Background indexing started")

    files = glob.glob(
        os.path.join(LOCAL_MUSIC_DIR, "**", "*.mp3"),
        recursive=True,
    )

    with INDEX_LOCK:
        existing = {e["path"] for e in LIB_INDEX}

    for path in files:
        if path in existing:
            continue
        meta = get_track_metadata(path)
        with INDEX_LOCK:
            LIB_INDEX.append(meta)

    save_index()
    INDEXING = False
    print(f"✅ Indexed {len(LIB_INDEX)} tracks")

# ---------------- Search ----------------

def find_local_track(query: str, cutoff=0.65):
    q = normalize(query)
    index = snapshot_index()

    # 1️⃣ Exact title match
    exact = [
        e["path"]
        for e in index
        if normalize(e.get("title")) == q
    ]
    if exact:
        return exact

    # 2️⃣ Exact key match (title - artist)
    exact_key = [
        e["path"]
        for e in index
        if e.get("key") == q
    ]
    if exact_key:
        return exact_key

    # 3️⃣ Fuzzy title match
    titles = [normalize(e.get("title")) for e in index]
    matches = difflib.get_close_matches(q, titles, n=1, cutoff=cutoff)
    if matches:
        return [
            e["path"]
            for e in index
            if normalize(e.get("title")) == matches[0]
        ]

    # 4️⃣ Fuzzy key match
    keys = [e["key"] for e in index]
    matches = difflib.get_close_matches(q, keys, n=1, cutoff=cutoff)
    if matches:
        return [
            e["path"]
            for e in index
            if e["key"] == matches[0]
        ]

    return []

def find_local_album(album_query: str, cutoff=0.7):
    q = normalize(album_query)
    index = snapshot_index()

    exact = [
        e["path"]
        for e in index
        if normalize(e.get("album")) == q
    ]
    if exact:
        return sorted(exact)

    albums = available_albums()
    close = difflib.get_close_matches(q, albums, n=1, cutoff=cutoff)
    if close:
        return sorted(
            e["path"]
            for e in index
            if normalize(e.get("album")) == close[0]
        )

    return []

def find_local_artist(artist_query: str, cutoff=0.7):
    q = normalize(artist_query)
    index = snapshot_index()

    exact = [
        e["path"]
        for e in index
        if normalize(e.get("artist")) == q
    ]
    if exact:
        return sorted(exact)

    artists = list({
        normalize(e.get("artist"))
        for e in index
        if e.get("artist")
    })

    close = difflib.get_close_matches(q, artists, n=1, cutoff=cutoff)
    if close:
        return sorted(
            e["path"]
            for e in index
            if normalize(e.get("artist")) == close[0]
        )

    return []

def find_local_genre(genre_query: str, cutoff=0.6):
    q = normalize(genre_query)
    index = snapshot_index()

    exact = [
        e["path"]
        for e in index
        if normalize(e.get("genre")) == q
    ]
    if exact:
        return exact

    genres = available_genres()
    close = difflib.get_close_matches(q, genres, n=1, cutoff=cutoff)
    if close:
        return [
            e["path"]
            for e in index
            if normalize(e.get("genre")) == close[0]
        ]

    return []

# ---------------- Routes ----------------

@app.post("/playlist")
def create_playlist(data: Prompt):
    prompt = data.prompt.strip()

    if prompt.lower().startswith("album:"):
        album = prompt.split(":", 1)[1]
        tracks = find_local_album(album)
        if not tracks:
            raise HTTPException(404, f"Album '{album}' not found")

    elif prompt.lower().startswith("genre:"):
        genre = prompt.split(":", 1)[1]
        tracks = find_local_genre(genre)
        if not tracks:
            raise HTTPException(404, f"No '{genre}' music found")
        random.shuffle(tracks)

    else:
        m = re.search(r"\bby\s+(.+)$", prompt, re.I)
        if m:
            tracks = find_local_artist(m.group(1))
            if not tracks:
                raise HTTPException(404, "Artist not found")
            random.shuffle(tracks)
        else:
            tracks = find_local_track(prompt)
            if not tracks:
                raise HTTPException(404, f"Couldn't find '{prompt}'")

    return {
        "tracks": [
            {
                "title": os.path.basename(p),
                "url": f"http://localhost:8000/local/{quote(os.path.relpath(p, LOCAL_MUSIC_DIR))}",
            }
            for p in tracks
        ]
    }

# ---------------- Static MP3 ----------------

@app.get("/local/{path:path}")
def serve_local_mp3(path: str):
    decoded = unquote(path)
    safe = os.path.normpath(decoded).lstrip("/")
    if safe.startswith(".."):
        raise HTTPException(400, "Invalid path")

    full = os.path.join(LOCAL_MUSIC_DIR, safe)
    if not os.path.isfile(full):
        raise HTTPException(404, "File not found")

    return StreamingResponse(open(full, "rb"), media_type="audio/mpeg")

@app.get("/genres")
def list_genres():
    return {"genres": available_genres()}

@app.get("/albums")
def list_albums():
    return {"albums": available_albums()}

# ---------------- Startup ----------------

if not load_index():
    threading.Thread(target=background_index_library, daemon=True).start()
