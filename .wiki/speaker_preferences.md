# nudle/speaker/preferences.py

**Role:** Per-user preference store for music taste and light room habits.

## Overview

Persists a JSON profile per enrolled speaker in `~/.nudle/preferences/{name}.json`. Two subsystems: music prompt history and light action history. Both use a weighted frequency counter that favors genuine engagement over casual use.

## Storage Format

```json
{
  "music": {
    "prompts": [
      {"prompt": "chill jazz", "count": 4, "last": "2026-11-15T20:03:11"},
      {"prompt": "80s rock",   "count": 2, "last": "2026-11-10T18:22:05"}
    ]
  },
  "lights": {
    "actions": [
      {"action": "off", "room": "bedroom", "count": 7, "last": "2026-11-25T22:10:00"},
      {"action": "on",  "room": "living room", "count": 3, "last": "2026-11-25T08:30:00"}
    ]
  }
}
```

Top 20 entries per list are kept; the rest are dropped.

## Music Methods

### `record_music(name, prompt, completed=False)`

Increments the count for `prompt` in the speaker's music history.
- `completed=True` (mpv exit code 0): weight 2
- `completed=False` (stopped/killed): weight 1

Called by `aiplay.py` after the playlist finishes or is stopped.

### `music_context(name, top_n=5) -> list[str]`

Returns up to `top_n` prompts sorted by count descending. Used by `aiplay._ask_ollama()` to personalize playlist generation.

## Light Methods

### `record_light(name, action, room)`

Increments the count for `(action, room)` in the speaker's light history. `room` is an empty string when no room was specified.

Called by `lights.handle()` after a successful HA service call.

### `preferred_room(name, action) -> str | None`

Returns the most frequently used non-empty room for the given action, or `None` if no history exists. Used by `lights.handle()` when the user says "turn off the lights" without specifying a room.

## Module Singleton

```python
prefs = SpeakerPreferences()
```

Import and use directly:
```python
from speaker.preferences import prefs
prefs.record_music("Gary", "chill jazz", completed=True)
```
