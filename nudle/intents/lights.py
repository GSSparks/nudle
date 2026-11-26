import os
import re
import requests

from speaker.preferences import prefs

_HA_URL = os.environ.get("NUDLE_HA_URL", "").rstrip("/")
_HA_TOKEN = os.environ.get("NUDLE_HA_TOKEN", "").strip()
_active_speaker: str | None = None

# Attributes that definitively identify a light entity regardless of domain
_LIGHT_ATTRS = {"brightness", "color_temp", "rgb_color", "hs_color", "color_mode", "supported_color_modes"}

# Friendly-name keywords that mark a switch as a light
_LIGHT_NAME_WORDS = {"light", "lights", "lamp", "lamps", "bulb", "bulbs",
                     "ceiling", "overhead", "chandelier", "sconce", "fixture", "led"}

# If any of these words appear in the friendly name, skip it — not a room light
_LIGHT_EXCLUDE_WORDS = {"robot", "mode", "vacuum", "mop", "litter", "sensor",
                        "monitor", "camera", "tv", "television", "plug", "outlet"}

# Domains that are definitively not lights — skip name-based matching for these
_SKIP_DOMAINS = {
    "binary_sensor", "sensor", "camera", "media_player", "weather", "sun",
    "zone", "person", "device_tracker", "automation", "script", "scene",
    "notify", "tts", "stt", "conversation", "ai_task", "assist_satellite",
    "wake_word", "update", "event", "image", "number", "select", "button",
}

_light_cache: list[dict] | None = None
_auto_pairs: dict[str, dict] = {}  # {"outdoor lights": {"on": "automation.outdoor_lights_on", "off": "..."}}


def set_speaker(name: str | None):
    global _active_speaker
    _active_speaker = name


def _headers():
    return {
        "Authorization": f"Bearer {_HA_TOKEN}",
        "Content-Type": "application/json",
    }


def _api(method, path, **kwargs):
    try:
        resp = requests.request(
            method,
            f"{_HA_URL}/api{path}",
            headers=_headers(),
            timeout=5,
            **kwargs,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"⚠️ HA error: {e} — {e.response.text[:300]}")
        return None
    except Exception as e:
        print(f"⚠️ HA error: {e}")
        return None


def discover_lights() -> int:
    """Query HA once and cache all light-controllable entities by attribute detection."""
    global _light_cache
    if not _HA_URL or not _HA_TOKEN:
        _light_cache = []
        return 0

    states = _api("GET", "/states")
    if not isinstance(states, list):
        print("⚠️ HA: discovery failed — /states did not return a list")
        _light_cache = []
        return 0

    found = []
    seen = set()
    all_switches = []

    for s in states:
        eid = s["entity_id"]
        domain = eid.split(".")[0]
        attrs = set(s.get("attributes", {}).keys())
        friendly = s.get("attributes", {}).get("friendly_name", "").lower()
        # Split on spaces AND hyphens; use substring match for compounds like "lamppostpost"
        tokens = set(re.split(r"[\s\-]+", friendly))
        has_light = (any(w in tokens for w in _LIGHT_NAME_WORDS) or
                     any(lw in tok for tok in tokens for lw in _LIGHT_NAME_WORDS))
        has_exclude = any(w in tokens for w in _LIGHT_EXCLUDE_WORDS)

        if domain == "light" or _LIGHT_ATTRS & attrs:
            # Definitively a light: standard domain or has brightness/color attributes
            found.append(s)
            seen.add(eid)
        elif domain not in _SKIP_DOMAINS:
            if domain == "switch":
                all_switches.append(s)
            if (has_light and not has_exclude and eid not in seen):
                found.append(s)
                seen.add(eid)

    if all_switches:
        print(f"💡 HA switches (not matched as lights): "
              + ", ".join(f"{s['entity_id']} ({s.get('attributes',{}).get('friendly_name','')})" for s in all_switches))

    if not found and all_switches:
        # Last resort: no named lights found — treat all switches as lights
        print(f"⚠️ HA: no named light entities found, falling back to all {len(all_switches)} switch entities")
        found = all_switches

    # Scan for automation on/off pairs (outdoor lights, etc.)
    auto_on: dict[str, str] = {}
    auto_off: dict[str, str] = {}
    for s in states:
        eid = s["entity_id"]
        if not eid.startswith("automation."):
            continue
        name = eid[len("automation."):]
        if name.endswith("_on"):
            auto_on[name[:-3]] = eid
        elif name.endswith("_off"):
            auto_off[name[:-4]] = eid

    _auto_pairs.clear()
    for base in sorted(set(auto_on) & set(auto_off)):
        friendly = base.replace("_", " ")
        _auto_pairs[friendly] = {"on": auto_on[base], "off": auto_off[base]}
        print(f"💡 HA automation pair: '{friendly}' → on={auto_on[base]}, off={auto_off[base]}")

    _light_cache = found
    if found:
        domains = sorted({e["entity_id"].split(".")[0] for e in found})
        names = [e.get("attributes", {}).get("friendly_name", e["entity_id"]) for e in found]
        print(f"💡 HA: {len(found)} light entities across {domains}: {names}")
    else:
        all_domains = sorted({s["entity_id"].split(".")[0] for s in states})
        print(f"⚠️ HA: no controllable light entities found. Domains: {all_domains}")
    return len(found)


def _get_lights() -> list[dict]:
    if _light_cache is None:
        discover_lights()
    return _light_cache or []


def _match_room(room: str, lights: list) -> list[str]:
    norm = room.lower().replace(" ", "_")
    matches = []
    for light in lights:
        eid = light["entity_id"]
        friendly = light.get("attributes", {}).get("friendly_name", "").lower()
        if norm in eid or room.lower() in friendly:
            matches.append(eid)
    return matches


_STRIP = re.compile(
    r"\b(turn|switch|set|dim|brighten|the|all|on|off|a|my)\b", re.IGNORECASE
)


def _extract_room(text: str) -> str | None:
    # "in the living room" / "in the bedroom"
    m = re.search(r"\bin\s+the\s+([\w ]+?)(?:\s+lights?|\s+lamps?|$)", text, re.IGNORECASE)
    if m:
        room = _STRIP.sub("", m.group(1)).strip()
        if room:
            return room
    # "the kitchen lights" / "bedroom lamps"
    m = re.search(r"\b([\w ]+?)\s+(?:lights?|lamps?)\b", text, re.IGNORECASE)
    if not m:
        return None
    room = _STRIP.sub("", m.group(1)).strip()
    return room if room else None


def _match_auto_pairs(room: str) -> list[dict]:
    """Return automation pair dicts whose friendly name overlaps with room."""
    norm = room.lower()
    return [pair for name, pair in _auto_pairs.items() if norm in name or name in norm]


def can_handle(text: str) -> bool:
    t = text.lower()
    has_light = bool(re.search(r"\b(light|lights|lamp|lamps)\b", t))
    has_action = bool(re.search(r"\b(turn|switch|on|off|dim|brighten|set)\b", t))
    return has_light and has_action


def handle(text: str) -> str:
    if not _HA_URL or not _HA_TOKEN:
        return "Home Assistant is not configured. Set NUDLE_HA_URL and NUDLE_HA_TOKEN in .env."

    t = text.lower()

    is_off = bool(re.search(r"\b(off|turn off|switch off)\b", t))
    is_dim = bool(re.search(r"\b(dim|dimmer|low|softer|soften)\b", t))
    is_bright = bool(re.search(r"\b(bright|brighter|brighten|full|max)\b", t))

    pct_match = re.search(r"(\d+)\s*(?:percent|%)", t)
    brightness_pct = int(pct_match.group(1)) if pct_match else None

    action = "off" if is_off else "on"
    room = _extract_room(text)

    if not room and _active_speaker:
        room = prefs.preferred_room(_active_speaker, action)
        if room:
            print(f"💡 Using preferred room for {_active_speaker}/{action}: {room}")

    lights = _get_lights()

    # Check automation pairs first (outdoor lights, etc.)
    if room:
        matched_pairs = _match_auto_pairs(room)
    else:
        matched_pairs = []

    if room:
        entity_ids = _match_room(room, lights)
        if not entity_ids and not matched_pairs:
            return f"I couldn't find any lights for {room}."
        location = f"the {room} lights"
    else:
        entity_ids = [l["entity_id"] for l in lights]
        location = "the lights"

    if not entity_ids and not matched_pairs:
        return "I couldn't find any lights to control."

    # homeassistant domain services work on any entity regardless of its own domain
    def _call(service, extra=None):
        data = {"entity_id": entity_ids, **(extra or {})}
        return _api("POST", f"/services/homeassistant/{service}", json=data)

    def _trigger_automations(auto_key: str):
        results = []
        for pair in matched_pairs:
            eid = pair[auto_key]
            r = _api("POST", "/services/automation/trigger", json={"entity_id": eid})
            results.append(r)
        # For "all lights off" with no room, trigger all _off automations
        if not room:
            for pair_data in _auto_pairs.values():
                eid = pair_data[auto_key]
                _api("POST", "/services/automation/trigger", json={"entity_id": eid})
        return results

    if is_off:
        ok = True
        if entity_ids:
            result = _call("turn_off")
            if result is None:
                ok = False
        _trigger_automations("off")
        if ok:
            prefs.record_light(_active_speaker, "off", room)
            return f"Turning off {location}."
        return "I had trouble reaching Home Assistant."

    extra = {}
    if brightness_pct is not None:
        extra["brightness_pct"] = brightness_pct
    elif is_dim:
        extra["brightness_pct"] = 30
    elif is_bright:
        extra["brightness_pct"] = 100

    ok = True
    if entity_ids:
        result = _call("turn_on", extra)
        if result is None:
            ok = False
    _trigger_automations("on")

    if not ok:
        return "I had trouble reaching Home Assistant."

    prefs.record_light(_active_speaker, "on", room)

    if brightness_pct is not None:
        return f"Setting {location} to {brightness_pct} percent."
    if is_dim:
        return f"Dimming {location}."
    if is_bright:
        return f"Brightening {location}."
    return f"Turning on {location}."
