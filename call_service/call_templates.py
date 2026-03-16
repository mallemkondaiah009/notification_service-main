"""
TwiML templates for outbound recruitment calls.

Voice: Polly.Kabir — Amazon Polly Neural, Indian English male.
Replaces: alice — US/UK accent, robotic, mispronounces Indian names.

Why Polly.Kabir:
  - Indian English accent — natural for Indian candidates
  - Neural engine — far more natural than standard TTS
  - Male voice — clear, professional, authoritative tone
  - Handles Indian names, salary figures, and city names correctly
  - Available free via Twilio (no extra Polly account needed)
"""

VOICE = "Polly.Raveena"
LANGUAGE = "en-IN"


def get_call_twiml(candidate_name: str, role_name: str, base_url: str) -> str:
    """
    Initial TwiML served when the call connects.
    Greets the candidate and asks if they are interested.
    Keeps listening for speech via <Gather>.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{base_url}/call/response/" method="POST" timeout="20" speechTimeout="auto" language="{LANGUAGE}">
        <Say voice="{VOICE}">
            Hello {candidate_name}, this is regarding your job application.
            We are currently hiring for the position of {role_name}.
            Are you interested in this position?
            Please speak your response after the beep.
        </Say>
    </Gather>
    <Say voice="{VOICE}">
        We did not receive your response. We will try again later. Goodbye.
    </Say>
</Response>"""


NO_INPUT_TWIML = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{VOICE}">
        We did not receive your response.
        We will try again later. Goodbye.
    </Say>
</Response>"""