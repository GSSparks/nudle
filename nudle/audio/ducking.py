# audio/ducking.py
import signal
from intents import music, radio

_ducked_players = []


def duck():
    """Pause all active audio players."""
    global _ducked_players
    _ducked_players = []

    for p in [music.player_process, radio.player_process]:
        if p and p.poll() is None:
            try:
                p.send_signal(signal.SIGSTOP)
                _ducked_players.append(p)
            except Exception as e:
                print(f"⚠️ Failed to duck player: {e}")


def unduck():
    """Resume previously ducked players."""
    global _ducked_players

    for p in _ducked_players:
        try:
            if p.poll() is None:
                p.send_signal(signal.SIGCONT)
        except Exception as e:
            print(f"⚠️ Failed to unduck player: {e}")

    _ducked_players = []
