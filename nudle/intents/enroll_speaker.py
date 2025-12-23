import re

def can_handle(text: str) -> bool:
    return bool(re.search(r"\bmy name is\b", text))

def extract_name(text: str) -> str:
    match = re.search(r"my name is\s+(\w+)", text)
    return match.group(1).lower() if match else "friend"
