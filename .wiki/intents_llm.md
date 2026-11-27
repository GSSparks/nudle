# nudle/intents/llm.py

**Role:** Ollama LLM fallback and smart intent router. Last handler in the chain — called only when no keyword-based intent matched.

## Overview

Sends the user's transcript to a local Ollama instance. The model is prompted to either return a structured routing JSON (if the request is about lights, music, weather, time, or radio) or answer directly in 1–2 spoken sentences for everything else.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `NUDLE_OLLAMA_URL` | `http://192.168.1.189:11434` | Ollama API base URL |
| `NUDLE_LLM_MODEL` | `qwen3.5:4b` | Model name |

## Routing vs. Chat

The system prompt gives the model few-shot examples showing when to return JSON:

```
"turn off the bedroom lights"  -> {"route":"lights","text":"turn off the bedroom lights"}
"play some chill jazz"         -> {"route":"music","text":"play some chill jazz"}
"what's the weather today"     -> {"route":"weather","text":"what is the weather today"}
"set a timer for 10 minutes"   -> {"route":"time","text":"set a timer for 10 minutes"}
"play kexp radio"              -> {"route":"radio","text":"play kexp"}
```

If the response starts with `{` and parses as a valid `{"route": ..., "text": ...}` object, `handle()` returns the dict. `main.py` dispatches it via `_LLM_ROUTE_MAP`.

If the model answers conversationally, `handle()` returns the raw string to be spoken directly.

## Return Value

`handle()` returns `str | dict`:
- `dict` with `"route"` and `"text"` keys — triggers re-dispatch in `main.py`
- `str` — spoken as-is

## Notes

- Uses `"think": False` and a 45-second timeout. Required for qwen3.5 to avoid multi-second reasoning delays.
- Connection errors return a user-facing message rather than raising.
