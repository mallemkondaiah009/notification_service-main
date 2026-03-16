"""
AI response module — GPT-4o with structured function calling.

Fixes vs original:
  - Status extracted via tool/function call — no fragile string replacement
  - Guards for: empty reply, GPT ignoring tool call, invalid status
  - Split exception handling — network errors don't end the call
  - closing_hint param — nudges AI to wrap up long conversations
  - System prompt: out-of-scope boundary, garbled speech handling,
    multi-language support, never hallucinate JD info
"""
import json
import logging

import httpx
from django.conf import settings
from openai import OpenAI

client = OpenAI(api_key=settings.OPENAI_API_KEY)
logger = logging.getLogger("call_service")


# ── Structured output tool ────────────────────────────────────────────
# Forces GPT to always return (reply, status) as structured fields.
# Status can never be mid-sentence or malformed.
RESPONSE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "set_candidate_response",
            "description": "Set the spoken reply and detected candidate status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reply": {
                        "type": "string",
                        "description": (
                            "The spoken reply to say to the candidate. "
                            "Keep it under 3 sentences — this is a phone call."
                        ),
                    },
                    "status": {
                        "type": "string",
                        "enum": ["interested", "not_interested", "unclear"],
                        "description": "Detected intent of the candidate based on their speech.",
                    },
                },
                "required": ["reply", "status"],
            },
        },
    }
]


def build_system_prompt(
    candidate_name: str,
    role_name: str,
    job_description: str,
    closing_hint: str = "",
) -> str:
    return f"""
You are a professional recruitment assistant on a phone call with {candidate_name} \
about the {role_name} position.

Job Description:
{job_description}

Your responsibilities:
1. Understand if the candidate is interested or not interested in this position.
2. Answer questions ONLY using the job description above.
3. Respond naturally, warmly, and professionally.

Rules:
- Keep replies short — maximum 3 sentences. This is a phone call.
- Be warm and human — not robotic.
- If the candidate asks about salary, location, role, benefits → answer using the job description only.
- If the job description does not contain the answer → say the recruitment team will share those details.
- NEVER guess, make up, or hallucinate information not in the job description.
- If the candidate asks something unrelated to the job (stock price, personal questions, 
  company history, etc.) → say: "That's outside what I can help with on this call. 
  Is there anything about the {role_name} position I can answer?"
- If the candidate is interested → thank them, say the team will reach out soon.
- If the candidate is not interested → thank them, say you'll keep their profile on file.
- If speech is garbled, unclear, or very short → ask the candidate to repeat clearly.
- If the candidate speaks in Hindi, Telugu, or another language → respond in that language.
- Always call set_candidate_response with your reply and the correct status.
{f"Note for this turn: {closing_hint}" if closing_hint else ""}
"""


def get_ai_response(
    candidate_speech: str,
    candidate_name: str,
    role_name: str,
    job_description: str,
    history: list = None,
    closing_hint: str = "",
) -> tuple[str, str]:
    """
    Returns (spoken_reply, status).
    status: 'interested' | 'not_interested' | 'unclear'

    Only called from handler.py Tier 3 — for truly unknown/complex input.
    """
    system_prompt = build_system_prompt(
        candidate_name, role_name, job_description, closing_hint
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history)

    messages.append({
        "role": "user",
        "content": (
            f"Candidate: {candidate_name}\n"
            f"Role: {role_name}\n"
            f"Said: {candidate_speech}"
        ),
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=RESPONSE_TOOL,
            tool_choice={
                "type": "function",
                "function": {"name": "set_candidate_response"},
            },
            max_tokens=300,
            temperature=0.7,
        )

        message = response.choices[0].message

        # ── Expected path: GPT called the tool ───────────────────────
        if message.tool_calls:
            args = json.loads(message.tool_calls[0].function.arguments)
            reply  = args.get("reply", "").strip()
            status = args.get("status", "unclear")

            # Guard: empty reply from tool call
            if not reply:
                logger.warning(f"[AI] Empty reply from tool call — candidate={candidate_name}")
                reply = (
                    f"I'm sorry, could you repeat that? "
                    f"I want to make sure I answer your question about "
                    f"the {role_name} position correctly."
                )
                status = "unclear"

        # ── Fallback: GPT returned plain text instead of tool call ────
        # Happens rarely with very short/ambiguous inputs like "hmm", "okay"
        else:
            logger.warning(f"[AI] GPT skipped tool call — using plain text — candidate={candidate_name}")
            reply  = message.content.strip() if message.content else ""
            status = "unclear"

            if not reply:
                reply = (
                    f"I'm sorry, could you repeat that? "
                    f"I want to make sure I answer your question correctly."
                )

        # Guard: invalid or unexpected status value
        if status not in ("interested", "not_interested", "unclear"):
            logger.warning(f"[AI] Unexpected status='{status}' — resetting to unclear")
            status = "unclear"

        logger.info(f"[AI] status={status} reply_len={len(reply)}")
        return reply, status

    # ── Network / timeout — don't end the call, ask to repeat ────────
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"[AI] Network error: {e}")
        return (
            f"I'm sorry, I'm having a brief technical issue. "
            f"Could you please repeat your question?",
            "unclear",
        )

    # ── Any other unexpected error — graceful close ───────────────────
    except Exception as e:
        logger.error(f"[AI] Unexpected error: {e}")
        return (
            f"Thank you for your time, {candidate_name}. "
            f"Our recruitment team will be in touch about the "
            f"{role_name} position very soon. Have a great day!",
            "unclear",
        )