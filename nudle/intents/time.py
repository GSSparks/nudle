# intents/time.py
import re
import os
import time
import threading
import subprocess
from datetime import datetime, timedelta

# ---------------- Globals ----------------

active_timers = []   # [{thread, start, duration}]
active_alarms = []   # [{thread, target}]

timer_cancel_event = threading.Event()
alarm_cancel_event = threading.Event()

DEFAULT_ALARM_SOUND = "../assets/lo-fi-alarm-clock-243766.mp3"  # Replace with your default alarm sound
ALARM_PLAYER = "mpg123"  # or "mpv"

# ---------------- Helpers ----------------

def speak(text: str):
    print(f"🗣️ {text}")

def now_str():
    return datetime.now().strftime("%-I:%M %p")

# ---------------- Number parsing ----------------

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60,
}

# ---------------- Timer logic ----------------

def timer_thread(start: float, duration: int):
    while time.time() - start < duration:
        if timer_cancel_event.is_set():
            return
        time.sleep(0.2)
    speak("⏲️ Timer finished.")

def set_timer(seconds: int):
    timer_cancel_event.clear()
    start = time.time()
    t = threading.Thread(
        target=timer_thread,
        args=(start, seconds),
        daemon=True
    )
    t.start()
    active_timers.append({
        "thread": t,
        "start": start,
        "duration": seconds
    })

def cancel_timer(all_timers=False):
    if not active_timers:
        return False

    timer_cancel_event.set()

    if all_timers:
        active_timers.clear()
    else:
        active_timers.pop()

    timer_cancel_event.clear()
    return True

def timer_remaining():
    if not active_timers:
        return None

    now = time.time()
    remaining = []
    for t in active_timers:
        elapsed = now - t["start"]
        left = int(t["duration"] - elapsed)
        if left > 0:
            remaining.append(left)

    return remaining

# ---------------- Alarm logic ----------------


def alarm_thread(target: datetime, sound_file: str = DEFAULT_ALARM_SOUND):
    while not alarm_cancel_event.is_set():
        if datetime.now() >= target:
            speak("⏰ Alarm going off.")
            if sound_file and os.path.isfile(sound_file):
                try:
                    # Play sound using system audio player
                    subprocess.Popen([ALARM_PLAYER, "-q", sound_file])
                except Exception as e:
                    speak(f"Failed to play alarm sound: {e}")
            return
        time.sleep(5)

def set_alarm(target: datetime, sound_file: str = DEFAULT_ALARM_SOUND):
    alarm_cancel_event.clear()
    t = threading.Thread(
        target=alarm_thread,
        args=(target, sound_file),
        daemon=True
    )
    t.start()
    active_alarms.append({
        "thread": t,
        "target": target,
        "sound": sound_file
    })

def cancel_alarm(all_alarms=False):
    if not active_alarms:
        return False

    alarm_cancel_event.set()

    if all_alarms:
        active_alarms.clear()
    else:
        active_alarms.pop()

    alarm_cancel_event.clear()
    return True

def snooze_alarm(minutes=10):
    if not active_alarms:
        return False

    cancel_alarm()
    new_target = datetime.now() + timedelta(minutes=minutes)
    set_alarm(new_target)
    return minutes

# ---------------- Formatting ----------------

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"

    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        if seconds:
            return f"{minutes} minutes and {seconds} seconds"
        return f"{minutes} minutes"

    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"{hours} hours and {minutes} minutes"
    return f"{hours} hours"

# ---------------- Parsing ----------------

def parse_duration(text: str) -> int | None:
    text = text.lower()
    tokens = text.split()
    normalized = []

    i = 0
    while i < len(tokens):
        if tokens[i] in NUMBER_WORDS:
            value = NUMBER_WORDS[tokens[i]]
            if value >= 20 and i + 1 < len(tokens) and tokens[i + 1] in NUMBER_WORDS:
                value += NUMBER_WORDS[tokens[i + 1]]
                i += 1
            normalized.append(str(value))
        else:
            normalized.append(tokens[i])
        i += 1

    text = " ".join(normalized)

    total = 0
    patterns = [
        (r"(\d+)\s*(second|seconds|sec|secs)", 1),
        (r"(\d+)\s*(minute|minutes|min|mins)", 60),
        (r"(\d+)\s*(hour|hours|hr|hrs)", 3600),
    ]

    for pattern, mult in patterns:
        for amt, _ in re.findall(pattern, text):
            total += int(amt) * mult

    return total if total > 0 else None

def parse_alarm_time(text: str) -> datetime | None:
    text = text.lower()
    now = datetime.now()
    current_is_pm = now.hour >= 12

    ampm = "pm" if "pm" in text else "am" if "am" in text else None
    nums = re.findall(r"\d+", text)
    if not nums:
        return None

    if len(nums[0]) >= 3:
        raw = nums[0]
        hour, minute = int(raw[:-2]), int(raw[-2:])
    elif len(nums) >= 2:
        hour, minute = int(nums[0]), int(nums[1])
    else:
        hour, minute = int(nums[0]), 0

    if hour > 23 or minute > 59:
        return None

    if ampm:
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
    elif current_is_pm and hour < 12:
        hour += 12

    target = now.replace(hour=hour, minute=minute, second=0)
    if target <= now:
        target += timedelta(days=1)

    return target

# ---------------- Intent interface ----------------

def can_handle(text: str) -> bool:
    text = text.lower()
    return any(k in text for k in [
        "time", "timer", "alarm", "wake me",
        "what time", "snooze", "cancel"
    ])

def handle_followup(text: str, context: dict):
    """
    Handles follow-up responses during a conversation.
    """
    intent = context.get("intent")

    # ---- TIMER FOLLOW-UP ----
    if intent == "timer":
        seconds = parse_duration(text)
        if not seconds:
            return {
                "prompt": "I didn’t catch the duration. Try again.",
                "intent": "timer",
                "expect": "duration"
            }

        set_timer(seconds)
        return f"Timer set for {format_duration(seconds)}."

    # ---- ALARM FOLLOW-UP ----
    if intent == "alarm":
        target = parse_alarm_time(text)
        if not target:
            return {
                "prompt": "I didn’t catch the time. Try again.",
                "intent": "alarm",
                "expect": "alarm_time"
            }

        set_alarm(target)
        return f"Alarm set for {target.strftime('%-I:%M %p')}."

    return "Sorry, I didn’t understand."

def handle(text: str):
    text = text.lower()

    # -------- STATUS --------
    if "how much time" in text or "time left" in text:
        remaining = timer_remaining()
        if not remaining:
            return "There are no active timers."
        return "Time remaining: " + ", ".join(
            format_duration(r) for r in remaining
        )

    # -------- CANCEL --------
    if "cancel" in text or "stop" in text or "turn off" in text:
        if "timer" in text:
            return (
                "All timers cancelled."
                if cancel_timer(all_timers="all" in text)
                else "There are no active timers."
            )
        if "alarm" in text:
            return (
                "All alarms cancelled."
                if cancel_alarm(all_alarms="all" in text)
                else "There are no active alarms."
            )

    # -------- SNOOZE --------
    if "snooze" in text:
        minutes = snooze_alarm()
        return f"Snoozed for {minutes} minutes." if minutes else "No alarm to snooze."

    # -------- TIME --------
    if "what time" in text or text.strip() == "time":
        return f"It’s {now_str()}."

    # -------- TIMER --------
    if "timer" in text:
        seconds = parse_duration(text)
        if not seconds:
            return {
                "prompt": "How long should I set the timer for?",
                "expect": "duration",
                "intent": "timer"
            }
        return f"Timer set for {format_duration(seconds)}."

    # -------- ALARM --------
    if "alarm" in text or "wake me" in text:
        target = parse_alarm_time(text)
        if not target:
            return {
                "prompt": "What time should I set the alarm for?",
                "expect": "alarm_time",
                "intent": "alarm"
            }
        set_alarm(target)
        return f"Alarm set for {target.strftime('%-I:%M %p')}."

    return "Sorry, I didn’t understand the time request."
