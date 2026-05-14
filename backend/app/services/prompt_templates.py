"""
Default prompt templates for pre-generated TTS audio system.

This module defines the default text templates for all prompt categories used in the
RecruiteAI voice interview platform. These templates are used to generate pre-cached
audio assets that reduce live-call latency.

Template Categories:
- Opener: Consent and call introduction
- Reprompt: Prompts to encourage elaboration or clarification
- Clarification: Requests for repetition or more detail
- Closing: Call conclusion phrases
- Filler: Short utterances to mask compute gaps

Requirements: 9.2, 10.1, 10.2, 11.1, 4.2
"""

# Opener Template
# Requirement 9.2: Standard consent opener for instant playback at call start
DEFAULT_OPENER_TEXT = (
    "Hello! I'm calling from the recruitment team. I'd like to ask you a few "
    "questions about your application. This call will be recorded for quality "
    "purposes. Do you have a few minutes to talk?"
)

# Reprompt Templates
# Requirement 10.1: Standard reprompts for fast and consistent recovery turns
DEFAULT_REPROMPT_TEXTS = {
    "reprompt_elaborate": "Can you tell me more about that?",
    "reprompt_example": "Can you give me an example?",
    "reprompt_clarify": "Could you clarify that?",
    "reprompt_detail": "Can you explain that in more detail?",
    "reprompt_background_interest": "Can you share your background and what excites you about this role?",
}

# Clarification Templates
# Requirement 10.2: Standard clarifications for recovery turns
DEFAULT_CLARIFICATION_TEXTS = {
    "clarification_repeat": "Could you repeat that?",
    "clarification_more": "Tell me more about that.",
    "clarification_im_here": "I'm here. Please continue.",
}

# Closing Templates
# Requirement 11.1: Standard closings for fast and polished call endings
DEFAULT_CLOSING_TEXTS = {
    "closing_thank_you": "Thank you for your time.",
    "closing_next_steps": "We'll be in touch soon.",
    "closing_goodbye": "Understood. Thank you for your time today. Goodbye.",
}

# Filler Templates
# Requirement 4.2: Short utterances to mask compute gaps
DEFAULT_FILLER_TEXTS = {
    "filler_understood": "Understood.",
    "filler_got_it": "Got it.",
    "filler_okay": "Okay.",
    "filler_thanks": "Thanks.",
    "filler_sure": "Sure.",
    "filler_one_moment": "One moment.",
}
