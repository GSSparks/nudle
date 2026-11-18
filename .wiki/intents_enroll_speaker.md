# nudle/intents/enroll_speaker.py

**Role:** Detects enrollment trigger phrases and extracts the speaker name.

## Functions

`can_handle(text)` returns True if `"my name is"` appears in the text (regex word-boundary match).

`extract_name(text)` captures the first word after `"my name is"` and lowercases it. Returns `"friend"` as a default if the pattern doesn't match.

## Usage

This module is not in the standard intent chain in `main.py`. Instead, `main.py` calls `can_handle()` directly before the normal `handle_command()` dispatch, and if it returns True, branches into the full enrollment flow (`enroll_speaker_safe()`).

## Notes

- Only first-name enrollment is supported (single `\w+` capture)
- If the speaker is already registered, `main.py` clears the existing record before re-enrolling
