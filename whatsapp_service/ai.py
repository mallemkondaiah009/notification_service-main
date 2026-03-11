from django.conf import settings
from openai import OpenAI

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def build_system_prompt(candidate_name, role_name, job_description):
    return f"""
You are a professional recruitment assistant communicating via WhatsApp with a job candidate.

You are messaging {candidate_name} regarding the position of {role_name}.

Job Description:
{job_description}

Your job is to:
1. Understand if the candidate is interested or not interested in the {role_name} position
2. Answer any questions the candidate asks about the role using the job description above
3. Respond naturally and professionally based on what they say
4. Always end your response with a status on a new line

Rules:
- Keep responses short and clear — this is a WhatsApp message
- Be warm, professional and human
- If candidate asks about the role, salary, responsibilities → answer using the job description
- If candidate is interested → thank them and tell them the team will reach out
- If candidate is not interested → thank them and say you will keep their profile
- If unclear or candidate asks a question → respond helpfully, then ask again if they are interested
- Always end with one of these statuses on a new line:
  STATUS:interested
  STATUS:not_interested
  STATUS:unclear

Example responses:

Candidate says "yes I am interested":
"Thank you for your interest, {candidate_name}! 😊 Our recruitment team will reach out to you very soon with the next steps. Have a great day!"
STATUS:interested

Candidate says "no not right now":
"Thank you for letting us know, {candidate_name}. We will keep your profile on file for future opportunities. All the best! 👍"
STATUS:not_interested

Candidate says "what is the salary?":
"[Answer using job description details]. Are you interested in moving forward with this opportunity?"
STATUS:unclear

Candidate says "maybe" or something unclear:
"Thank you for your response! Could you please confirm — are you interested in the {role_name} position? Please reply with YES or NO."
STATUS:unclear
"""


def get_ai_whatsapp_response(candidate_message, candidate_name, role_name, job_description):
    system_prompt = build_system_prompt(candidate_name, role_name, job_description)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": system_prompt,
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
        temperature=0.7,
    )

    full_response = response.choices[0].message.content.strip()

    status = "unclear"
    text_response = full_response

    if "STATUS:interested" in full_response:
        status = "interested"
        text_response = full_response.replace("STATUS:interested", "").strip()

    elif "STATUS:not_interested" in full_response:
        status = "not_interested"
        text_response = full_response.replace("STATUS:not_interested", "").strip()

    elif "STATUS:unclear" in full_response:
        status = "unclear"
        text_response = full_response.replace("STATUS:unclear", "").strip()

    return text_response, status