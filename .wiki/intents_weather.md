# nudle/intents/weather.py

**Role:** Intent handler for weather queries via wttr.in.

## Intent Interface

`can_handle(text)` matches: `weather`, `temperature`.

`handle(text)` detects the timeframe (today / tomorrow / outside), fetches wttr.in, and returns a speech-friendly string.

## Implementation

Default location: ZIP code `46711`.  
API: `https://wttr.in/{location}?u&format={fmt}` with `u` flag for US customary units (Fahrenheit, mph).

Format strings:
- Current: `%C%t` (condition + temperature)
- Tomorrow: `%C%t%w` (condition + temperature + wind)

`_clean_for_speech(text)` converts:
- `°F` → `degrees fahrenheit`
- `mph` → `miles per hour winds`
- Strips non-ASCII, removes `+` signs, converts `-` to `negative`

## Notes

- Network call is synchronous (10 s timeout); exceptions return a fallback string
- The `&` in the URL is escaped as `\&` in the f-string to prevent shell expansion (this would be a bug if the URL is ever passed to a shell; it's fine for `requests.get`)
