# intents/radio.py
import subprocess
import threading
import time

PLAYER_CMD = "mpv"

player_process = None
stop_event = threading.Event()

# ---------------- Stations ----------------
RADIO_STATIONS = {
    "npr": {
        "name": "NPR",
        "url": "https://npr-ice.streamguys1.com/live.mp3",
    },
    "kexp": {
        "name": "KEXP Seattle",
        "url": "https://kexp-mp3-128.streamguys1.com/kexp128.mp3",
    },
    "lofi": {
        "name": "Lo-fi Radio",
        "url": "https://streams.ilovemusic.de/iloveradio107.mp3",
    },
    "bbc": {
        "name": "BBC World Service",
        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
    },
    "103.9": {
        "name": "Wayne FM",
        "url": "https://prod-35-174-10-46.amperwave.net/adamsradio-wwfwfmaac-ibc1",
    },
    "relaxing piano": {
        "name": "Piano Solo Radio",
        "url": "https://pianosolo.streamguys1.com/live",
    },
}

# ---------------- Playback ----------------
def stop_radio():
    global player_process
    stop_event.set()
    if player_process and player_process.poll() is None:
        player_process.terminate()
    stop_event.clear()

def play_station(station):
    global player_process
    stop_radio()

    print(f"📻 Tuning to {station['name']}")
    player_process = subprocess.Popen(
        [PLAYER_CMD, "--no-video", "--quiet", station["url"]],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    while player_process.poll() is None:
        if stop_event.is_set():
            player_process.terminate()
            break
        time.sleep(0.5)

# ---------------- Intent Interface ----------------
def can_handle(text: str) -> bool:
    text = text.lower()
    return (
        "radio" in text
        or any(name in text for name in RADIO_STATIONS)
    )

def handle(text: str):
    text = text.lower()

    # Stop commands
    if any(k in text for k in ["stop", "turn off", "silence"]):
        stop_radio()
        return "Radio stopped."

    # Find station
    for key, station in RADIO_STATIONS.items():
        if key in text:
            threading.Thread(
                target=play_station,
                args=(station,),
                daemon=True,
            ).start()
            return f"Playing {station['name']}."

    return "I don't recognize that radio station."
