# nudle/intents/radio.py

**Role:** Intent handler for internet radio streams.

## Stations

| Key | Name | Stream |
|-----|------|--------|
| `npr` | NPR | streamguys1 live.mp3 |
| `kexp` | KEXP Seattle | kexp128.mp3 |
| `lofi` | Lo-fi Radio | iloveradio107.mp3 |
| `bbc` | BBC World Service | bbcmedia live |
| `103.9` | Wayne FM | amperwave |
| `relaxing piano` | Piano Solo Radio | pianosolo live |

## Intent Interface

`can_handle(text)` returns True if `"radio"` is in the text or any station key appears.

`handle(text)` checks for stop keywords first (`stop`, `turn off`, `silence`), then matches station keys.  
Playback runs in a daemon thread via `play_station()`.

## Playback

Uses `mpv --no-video --quiet` for each station.  
`player_process` is a module-level global (read by `audio/ducking.py` and `tts/piper.py`).  
`stop_radio()` terminates the process and sets `stop_event`.

## Notes

- Only one station plays at a time; `play_station()` calls `stop_radio()` before starting a new stream
- The player loop in `play_station()` polls `stop_event` every 500 ms
