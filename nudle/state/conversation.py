class ConversationState:
    def __init__(self):
        self.speaker = None
        self.confidence = 0.0

    def set_speaker(self, name, confidence):
        self.speaker = name
        self.confidence = confidence
