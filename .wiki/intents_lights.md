# nudle/intents/lights.py

**Role:** Intent handler for controlling lights via the Home Assistant REST API.

## Overview

Discovers all controllable light entities at startup, then handles turn-on/off, dimming, and brightness commands. Supports entities across any HA domain (switch, light, etc.) and automation on/off pairs for entities that have no direct switch (e.g. outdoor lights).

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `NUDLE_HA_URL` | `` | Home Assistant base URL (e.g. `https://ha.example.com`) |
| `NUDLE_HA_TOKEN` | `` | Long-lived access token |

Both must be set or all calls return an error message immediately.

## Entity Discovery (`discover_lights()`)

Called once at startup by `main.py`. Queries `/api/states` and classifies entities:

1. **Attribute-based (definitive):** entity has any of `brightness`, `color_temp`, `rgb_color`, `hs_color`, `color_mode`, `supported_color_modes` → always a light regardless of domain
2. **Domain `light`:** always included
3. **Name-based (across non-sensor domains):** friendly name contains a light keyword (`light`, `lamp`, `bulb`, `ceiling`, `chandelier`, etc.) and no exclude keyword (`robot`, `mop`, `litter`, `monitor`, `camera`, etc.) — splits on spaces **and** hyphens, with substring matching for compound words like "lamppostpost"
4. **Last resort:** if no lights found by the above, all switch entities are treated as lights
5. **Automation pairs:** scans all `automation.*` entities for `_on`/`_off` suffix pairs; groups them by common base name as controllable pairs

Results are cached in `_light_cache` and `_auto_pairs`. Re-discovery requires a restart.

### Automation Pairs

For each matched pair (e.g. `automation.outdoor_lights_on` / `automation.outdoor_lights_off`):
- Stored in `_auto_pairs` as `{"outdoor lights": {"on": "automation.outdoor_lights_on", "off": "..."}}`
- Triggered via `POST /api/services/automation/trigger` (not `homeassistant/turn_on`)

## Room Matching

`_match_room(room, lights)` matches against entity IDs (normalized `_`) and friendly names (substring).

`_match_auto_pairs(room)` returns automation pairs whose friendly key overlaps with the requested room.

Room is extracted from the utterance via two patterns:
- "in the [room]" / "in the [room] lights"
- "[room] lights" / "[room] lamps"

If no room is extracted, `prefs.preferred_room()` returns the most-used room for this speaker and action.

## Service Calls

Regular entities use the universal `homeassistant/turn_on|off` service (works across `switch`, `light`, and other domains).

Automation pairs use `automation/trigger` with the specific entity ID.

## Brightness

| Utterance | brightness_pct sent |
|-----------|-------------------|
| "dim the lights" | 30 |
| "brighten the lights" | 100 |
| "set the lights to 60 percent" | 60 |
| plain on | (omitted — HA restores last level) |

## Per-User Preferences

After a successful action, `prefs.record_light(speaker, action, room)` is called. This feeds `prefs.preferred_room()` for future room-less commands.

## Module-level Globals

| Name | Purpose |
|------|---------|
| `_light_cache` | List of discovered light entity state dicts; `None` until first discovery |
| `_auto_pairs` | Dict of automation on/off pairs keyed by friendly base name |
| `_active_speaker` | Set by `set_speaker()` from main.py before each command |
