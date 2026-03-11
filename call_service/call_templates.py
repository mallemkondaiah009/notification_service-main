def get_call_twiml(candidate_name, role_name, base_url):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{base_url}/call/response/" method="POST" timeout="20" speechTimeout="auto" language="en-IN">
        <Say voice="alice">
            Hello {candidate_name}, this is regarding your job application.
            We are currently hiring for the position of {role_name}.
            Are you interested in this position?
            Please speak your response after the beep.
        </Say>
    </Gather>
    <Say voice="alice">
        We did not receive your response. We will try again later. Goodbye.
    </Say>
</Response>"""


NO_INPUT_TWIML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">
        We did not receive your response.
        We will try again later. Goodbye.
    </Say>
</Response>"""