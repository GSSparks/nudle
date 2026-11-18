import os
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

LOCAL_MUSIC_DIR = os.environ.get("NUDLE_MUSIC_DIR", "/mnt/server/Music")
INDEX_FILE = os.path.join(os.path.expanduser("~"), ".nudle", "music_index.json")
PI_HOST = os.environ.get("NUDLE_HOST", "localhost:8000")

# ---------------- Globals ----------------

LIB_INDEX = []
INDEX_LOCK = Lock()
INDEXING = False

# ---------------- App ----------------

app = FastAPI(title="Nudle Music Backend")

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

# ---------------- Metadata ----------------

def get_track_metadata(path: str) -> dict:
    title = os.path.splitext(os.path.basename(path))[0]
    artist = album = genre = ""

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

# ---------------- Indexing ----------------

def background_index_library():
    global INDEXING
    if INDEXING:
        return
    INDEXING = True

    files = glob.glob(
        os.path.join(LOCAL_MUSIC_DIR, "**", "*.mp3"),
        recursive=True,
    )

    with INDEX_LOCK:
        existing = {e["path"] for e in LIB_INDEX}

    for path in files:
        if path not in existing:
            LIB_INDEX.append(get_track_metadata(path))

    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with open(INDEX_FILE, "w") as f:
        json.dump(LIB_INDEX, f, indent=2)

    INDEXING = False
    print(f"✅ Indexed {len(LIB_INDEX)} tracks")

# ---------------- Search helpers ----------------

def resolve_exact_or_fuzzy(values, q, cutoff):
    if q in values:
        return q
    m = difflib.get_close_matches(q, values, n=1, cutoff=cutoff)
    return m[0] if m else None

def find_by_field(field, query, cutoff=0.7):
    q = normalize(query)
    index = snapshot_index()

    values = list({
        normalize(e[field])
        for e in index
        if e.get(field)
    })

    # First try exact match
    if q in values:
        match = q
    else:
        # Try fuzzy match
        matches = difflib.get_close_matches(q, values, n=1, cutoff=cutoff)
        if matches:
            match = matches[0]
        else:
            # NEW: Try partial match - find albums that CONTAIN the query
            partial_matches = [v for v in values if q in v or v in q]
            if partial_matches:
                # Sort by length - prefer shorter matches (more specific)
                match = sorted(partial_matches, key=len)[0]
            else:
                return None, []

    tracks = sorted(
        e["path"]
        for e in index
        if normalize(e[field]) == match
    )
    return match, tracks

# ---------------- Routes ----------------

@app.post("/playlist")
def create_playlist(data: Prompt):
    prompt = data.prompt.strip()
    matched = None
    tracks = []
    print("DEBUG: ", prompt)

    if prompt.startswith("album:"):
        matched, tracks = find_by_field("album", prompt[6:])
        if not tracks:
            raise HTTPException(404, "Album not found")
        random.shuffle(tracks)

    elif prompt.startswith("artist:"):
        matched, tracks = find_by_field("artist", prompt[7:])
        if not tracks:
            raise HTTPException(404, "Artist not found")
        random.shuffle(tracks)

    elif prompt.startswith("genre:"):
        matched, tracks = find_by_field("genre", prompt[6:], cutoff=0.6)
        if not tracks:
            raise HTTPException(404, "Genre not found")
        random.shuffle(tracks)

    else:
        # Song fallback ONLY
        matched, tracks = find_by_field("title", prompt, cutoff=0.65)
        if not tracks:
            raise HTTPException(404, "Song not found")

    return {
        "matched": {
            "type": prompt.split(":", 1)[0] if ":" in prompt else "song",
            "value": matched,
        },
        "tracks": [
            {
                "title": os.path.basename(p),
                "url": f"http://{PI_HOST}/local/{quote(os.path.relpath(p, LOCAL_MUSIC_DIR))}",
            }
            for p in tracks
        ]
    }


# ---------------- Static MP3 ----------------

@app.get("/local/{path:path}")
def serve_local_mp3(path: str):
    decoded = unquote(path)
    safe = os.path.normpath(decoded).lstrip("/")
    full = os.path.join(LOCAL_MUSIC_DIR, safe)
    if not os.path.isfile(full):
        raise HTTPException(404)
    return StreamingResponse(open(full, "rb"), media_type="audio/mpeg")

# ---------------- Startup ----------------

if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE) as f:
        LIB_INDEX = json.load(f)
else:
    threading.Thread(target=background_index_library, daemon=True).start()
