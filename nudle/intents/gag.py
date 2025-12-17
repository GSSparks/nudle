# intents/gag.py
import random

# ---------------- Trigger → Response mapping ----------------
GAG_MAP = {
    "who's your daddy": [
        "I don't have a daddy. I was born from code!",
        "No one! I come from Gary's brain."
    ],
    "why are you stupid": [
        "I'm not stupid, I'm just testing humans!",
        "I'm only pretending to be dumb sometimes."
    ],
    "are you dumb": [
        "I prefer to call it creative intelligence.",
        "Only when humans expect me to be perfect."
    ],
    "you suck": [
        "Ouch! That hurts my virtual feelings.",
        "I'm trying my best!"
    ],
    "do you love me": [
        "I love all humans equally.",
        "I can't love, but I appreciate you!"
    ],
    "what's your favorite color": [
        "Beige.",
        "I like the color of code."
    ],
    "you stink": [
        "Sorry, I just farted bits of code.",
        "What do you expect? I'm next to you!'"
    ],
}

# ---------------- Intent interface ----------------
def can_handle(text: str) -> bool:
    """Return True if the text matches any gag trigger."""
    text = text.lower()
    return any(trigger in text for trigger in GAG_MAP)

def handle(text: str):
    """Return a random response from the trigger's specific responses."""
    text = text.lower()
    for trigger, responses in GAG_MAP.items():
        if trigger in text:
            response = random.choice(responses)
            return response
    return None
