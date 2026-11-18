# nudle/state/conversation.py

**Role:** Data class for tracking conversation state (speaker identity and confidence).

## Class: `ConversationState`

```python
class ConversationState:
    speaker: str | None
    confidence: float
    set_speaker(name, confidence)
```

## Current Usage

This class is defined but not currently instantiated in `main.py`. Conversation state is tracked there using plain module-level globals (`conversation_context` dict, `conversation_active` bool, `last_interaction_time` float) rather than this class.

This file appears to be a placeholder for a future refactor that would centralize conversation state management.
