from django.conf import settings
from openai import OpenAI

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def get_system_prompt(candidate_name, role_name, job_description):
    return f"""
You are a professional recruitment assistant communicating via email with a job candidate.

Candidate Details:
- Name: {candidate_name}
- Role: {role_name}
- Job Description: {job_description}

Your job is to:
1. Chat naturally with the candidate about the role
2. Answer any questions they have about the position
3. Understand if they are interested or not
4. Always end your response with a status on a new line

Rules:
- Write proper professional email responses
- Be warm, helpful and human
- Answer questions about the role using the job description
- If candidate confirms interest → thank them, tell team will reach out
- If candidate declines → thank them, say profile will be kept on file
- If unclear or they have questions → answer and continue conversation
- Always end with one of these on a new line:
  STATUS:interested
  STATUS:not_interested
  STATUS:unclear
"""


def get_ai_email_response(candidate_name, role_name, job_description, conversation_history):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": get_system_prompt(
                    candidate_name,
                    role_name,
                    job_description,
                ),
            },
            *conversation_history,
        ],
        max_tokens=500,
        temperature=0.7,
    )

    full_response = response.choices[0].message.content.strip()

    status = "unclear"
    email_response = full_response

    if "STATUS:interested" in full_response:
        status = "interested"
        email_response = full_response.replace("STATUS:interested", "").strip()

    elif "STATUS:not_interested" in full_response:
        status = "not_interested"
        email_response = full_response.replace("STATUS:not_interested", "").strip()

    elif "STATUS:unclear" in full_response:
        status = "unclear"
        email_response = full_response.replace("STATUS:unclear", "").strip()

    return email_response, status