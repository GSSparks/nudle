import json
import os
from datetime import datetime

_PREFS_DIR = os.path.expanduser("~/.nudle/preferences")


class SpeakerPreferences:
    def __init__(self):
        os.makedirs(_PREFS_DIR, exist_ok=True)
        self._cache: dict[str, dict] = {}

    def _path(self, name: str) -> str:
        return os.path.join(_PREFS_DIR, f"{name.lower()}.json")

    def _load(self, name: str) -> dict:
        if name not in self._cache:
            path = self._path(name)
            if os.path.exists(path):
                with open(path) as f:
                    self._cache[name] = json.load(f)
            else:
                self._cache[name] = {
                    "music": {"prompts": []},
                    "lights": {"actions": []},
                }
        return self._cache[name]

    def _save(self, name: str):
        with open(self._path(name), "w") as f:
            json.dump(self._cache[name], f, indent=2)

    def _bump(self, entries: list, match_fn, new_entry: dict, weight: int = 1):
        for entry in entries:
            if match_fn(entry):
                entry["count"] += weight
                entry["last"] = datetime.now().isoformat()
                return
        new_entry["count"] = weight
        new_entry["last"] = datetime.now().isoformat()
        entries.append(new_entry)
        entries.sort(key=lambda x: x["count"], reverse=True)
        del entries[20:]  # keep top 20

    # ---- music ---------------------------------------------------------------

    def record_music(self, name: str, prompt: str, completed: bool = False):
        if not name:
            return
        data = self._load(name)
        # completed playlist weighs 2x a skip/stop so genuine taste rises faster
        self._bump(
            data["music"]["prompts"],
            lambda e: e["prompt"] == prompt,
            {"prompt": prompt},
            weight=2 if completed else 1,
        )
        self._save(name)

    def music_context(self, name: str, top_n: int = 5) -> list[str]:
        """Return up to top_n past music prompts, most frequent first."""
        if not name:
            return []
        return [e["prompt"] for e in self._load(name)["music"]["prompts"][:top_n]]

    # ---- lights --------------------------------------------------------------

    def record_light(self, name: str, action: str, room: str | None):
        if not name:
            return
        data = self._load(name)
        room = room or ""
        self._bump(
            data["lights"]["actions"],
            lambda e: e["action"] == action and e["room"] == room,
            {"action": action, "room": room},
        )
        self._save(name)

    def preferred_room(self, name: str, action: str) -> str | None:
        """Return the most frequently used room for this action, or None."""
        if not name:
            return None
        matches = [
            e for e in self._load(name)["lights"]["actions"]
            if e["action"] == action and e["room"]
        ]
        return matches[0]["room"] if matches else None


# module-level singleton — import and use directly
prefs = SpeakerPreferences()
