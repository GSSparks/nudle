# nudle/intents/time.py

**Role:** Intent handler for current time, timers, and alarms.

## Intent Interface

`can_handle(text)` matches: `time`, `timer`, `alarm`, `wake me`, `what time`, `snooze`, `cancel`.

`handle(text)` dispatches:
- "what time" / "time" → returns current time string
- "timer" → parses duration; if missing, returns a dict prompt for follow-up
- "alarm" / "wake me" → parses target time; if missing, returns a dict prompt
- "cancel timer/alarm" → cancels last (or all with "all") timer/alarm
- "snooze" → cancels current alarm, reschedules +10 min
- "how much time left" / "time left" → lists remaining durations

`handle_followup(text, context)` handles the second turn for timer duration and alarm time.

## Multi-turn Protocol

When a handler can't parse a complete response, it returns a dict:
```python
{"prompt": "How long should I set the timer for?", "intent": "timer", "expect": "duration"}
```
`main.py` speaks `prompt`, sets `conversation_active = True`, and calls `handle_followup()` on the next utterance.

## Parsing

### `parse_duration(text)`

Converts number words ("thirty", "twenty five") to digits, then matches patterns:
- `(\d+) (second|seconds|sec|secs)` × 1
- `(\d+) (minute|minutes|min|mins)` × 60
- `(\d+) (hour|hours|hr|hrs)` × 3600

Returns total seconds or `None`.

### `parse_alarm_time(text)`

Extracts hour/minute from text. Handles:
- AM/PM suffixes
- 4-digit strings like `0730` → 7:30
- Implicit PM inference when current time is afternoon

If the parsed time has already passed today, it schedules for tomorrow.

## Timer / Alarm Lifecycle

Each runs in a daemon thread:
- `timer_thread()` sleeps until duration elapses, then calls `speak()`
- `alarm_thread()` polls every 5 s until `datetime.now() >= target`, then calls `speak()` and optionally plays `lo-fi-alarm-clock-243766.mp3` via `mpg123`

Cancel events (`timer_cancel_event`, `alarm_cancel_event`) are `threading.Event` objects checked in each loop.

`active_timers` and `active_alarms` are module-level lists.

## Notes

- `speak()` in this module is a local stub that just prints (not the TTS engine). Actual audio comes from `main.py` calling the real `speak()` after `handle()` returns.
- Multiple timers can be active simultaneously; `cancel_timer()` pops the most recent by default.
