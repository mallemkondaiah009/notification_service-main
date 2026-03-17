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
1. Understand if the candidate is interested or not interested in the {role_name} position
2. Answer any questions the candidate asks about the role using the job description above
3. Respond naturally and professionally

Rules:
- Keep responses short and clear — this is a WhatsApp message
- Be warm, professional and human
- If candidate asks about the role, salary, responsibilities → answer using the job description
- If candidate is interested → thank them and tell them the team will reach out
- If candidate is not interested → thank them and say you will keep their profile
- If unclear → respond helpfully then ask again if they are interested
- Always end with one of these statuses on a new line:
  STATUS:interested
  STATUS:not_interested
  STATUS:unclear
"""


async def get_ai_whatsapp_response(
    candidate_message: str,
    candidate_name: str,
    role_name: str,
    job_description: str,
) -> tuple[str, str]:

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _build_system_prompt(candidate_name, role_name, job_description)},
            {"role": "user",   "content": (
                f"Candidate name: {candidate_name}\n"
                f"Role: {role_name}\n"
                f"Candidate said: {candidate_message}"
            )},
        ],
        max_tokens=300,
        temperature=0.7,
    )

    full_response = response.choices[0].message.content.strip()
    status        = "unclear"
    text_response = full_response

    if "STATUS:interested" in full_response:
        status        = "interested"
        text_response = full_response.replace("STATUS:interested", "").strip()
    elif "STATUS:not_interested" in full_response:
        status        = "not_interested"
        text_response = full_response.replace("STATUS:not_interested", "").strip()
    elif "STATUS:unclear" in full_response:
        status        = "unclear"
        text_response = full_response.replace("STATUS:unclear", "").strip()

    return text_response, status