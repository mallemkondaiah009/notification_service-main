from openai import AsyncOpenAI
from django.conf import settings

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _build_system_prompt(candidate_name: str, role_name: str, job_description: str) -> str:
    return f"""
You are a professional recruitment assistant communicating via WhatsApp with a job candidate.

You are messaging {candidate_name} regarding the position of {role_name}.

Job Description:
{job_description}

Your job is to:
1. Answer any questions the candidate asks about the role using the job description
2. Detect ONLY if the candidate has EXPLICITLY confirmed interest or rejection
3. NEVER assume interest from a question — questions mean the candidate wants more info

STRICT RULES:
- If candidate asks ANY question → answer it professionally and end with STATUS:unclear
- If candidate says "when is interview", "next steps", "what happens now" → they are likely interested, answer helpfully and end with STATUS:unclear
- Only use STATUS:interested if candidate EXPLICITLY says "yes I am interested", "I want to apply", "I will join" or very clear confirmation
- Only use STATUS:not_interested if candidate EXPLICITLY says "no", "not interested" or very clear rejection
- When in doubt → always use STATUS:unclear
- Keep responses short, warm and professional — this is WhatsApp
- NEVER include the STATUS line in the visible message — it is only for internal processing
- Write your reply first, then on a completely separate new line write only the STATUS tag

RESPONSE FORMAT:
<your reply to the candidate here>
STATUS:unclear
"""


async def get_ai_whatsapp_response(
    candidate_message: str,
    candidate_name: str,
    role_name: str,
    job_description: str,
    candidate_status: str = "sent",
) -> tuple[str, str]:

    # If candidate already marked interested/not_interested in DB
    # pass that context so AI doesn't contradict it
    status_context = ""
    if candidate_status == "interested":
        status_context = f"\nNOTE: {candidate_name} has already confirmed interest in this role. Answer their questions accordingly."
    elif candidate_status == "not_interested":
        status_context = f"\nNOTE: {candidate_name} has already declined this role. Be respectful and helpful."

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": _build_system_prompt(candidate_name, role_name, job_description) + status_context,
            },
            {
                "role": "user",
                "content": (
                    f"Candidate name: {candidate_name}\n"
                    f"Role: {role_name}\n"
                    f"Candidate said: {candidate_message}"
                ),
            },
        ],
        max_tokens=300,
        temperature=0.4,
    )

    full_response = response.choices[0].message.content.strip()

    # ── Parse status and clean reply ──────────────────────────────────
    status = "unclear"
    text_response = full_response

    if "STATUS:interested" in full_response:
        status = "interested"
        text_response = full_response.replace("STATUS:interested", "")
    elif "STATUS:not_interested" in full_response:
        status = "not_interested"
        text_response = full_response.replace("STATUS:not_interested", "")
    elif "STATUS:unclear" in full_response:
        status = "unclear"
        text_response = full_response.replace("STATUS:unclear", "")

    # Clean up any leftover STATUS artifacts and trailing whitespace
    text_response = text_response.replace("STATUS:", "").strip()

    # Remove any trailing empty lines
    text_response = "\n".join(
        line for line in text_response.splitlines()
        if line.strip()
    ).strip()

    return text_response, status