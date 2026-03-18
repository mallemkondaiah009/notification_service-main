import logging

from openai import AsyncOpenAI
from django.conf import settings

logger = logging.getLogger("whatsapp.ai")

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _build_system_prompt(
    candidate_name: str,
    role_name: str,
    job_description: str,
    candidate_status: str,
) -> str:
    status_note = ""
    if candidate_status == "interested":
        status_note = (
            f"\nNOTE: {candidate_name} has already confirmed interest. "
            f"Answer their questions helpfully. Do not ask them again if they are interested."
        )
    elif candidate_status == "not_interested":
        status_note = (
            f"\nNOTE: {candidate_name} has previously declined. "
            f"Be respectful. If they ask questions, answer them helpfully."
        )

    return f"""You are a professional recruitment assistant communicating via WhatsApp.

You are messaging {candidate_name} about the {role_name} position.

Job Description:
{job_description}

RULES:
- Answer questions using the job description
- Keep responses short and professional — this is WhatsApp
- NEVER assume interest from a question
- Only STATUS:interested for very explicit confirmations like "yes I am interested", "I want to apply"
- Only STATUS:not_interested for very explicit rejections like "no", "not interested"
- Always default to STATUS:unclear when in doubt
- Write your reply first, then STATUS on a new line
- NEVER show STATUS in the visible message{status_note}

FORMAT:
<reply>
STATUS:unclear"""


async def get_ai_whatsapp_response(
    candidate_message: str,
    candidate_name: str,
    role_name: str,
    job_description: str,
    candidate_status: str = "sent",
    history: list | None = None,
) -> tuple[str, str]:

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(
                candidate_name, role_name, job_description, candidate_status
            ),
        }
    ]

    # Inject last N conversation turns
    if history:
        for entry in history:
            role = "user" if entry["sender"] == "candidate" else "assistant"
            # Skip system/internal messages from history
            if entry.get("direction") == "inbound" or entry["sender"] == "candidate":
                messages.append({"role": "user", "content": entry["message"]})
            elif entry["sender"] in ("ai", "system"):
                messages.append({"role": "assistant", "content": entry["message"]})

    messages.append({
        "role": "user",
        "content": candidate_message,
    })

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=300,
            temperature=0.4,
        )

        full_response = response.choices[0].message.content.strip()

        status        = "unclear"
        text_response = full_response

        if "STATUS:interested" in full_response:
            status        = "interested"
            text_response = full_response.replace("STATUS:interested", "")
        elif "STATUS:not_interested" in full_response:
            status        = "not_interested"
            text_response = full_response.replace("STATUS:not_interested", "")
        elif "STATUS:unclear" in full_response:
            status        = "unclear"
            text_response = full_response.replace("STATUS:unclear", "")

        # Clean up any leftover STATUS text
        text_response = text_response.replace("STATUS:", "").strip()
        text_response = "\n".join(
            line for line in text_response.splitlines() if line.strip()
        ).strip()

        return text_response, status

    except Exception as exc:
        logger.error("[AI] get_ai_whatsapp_response failed — %s", exc)
        return (
            f"Sorry {candidate_name}, I'm having trouble processing your message right now. "
            f"Please try again in a moment.",
            "unclear",
        )