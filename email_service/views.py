import resend
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from candidate.models import Candidate
from delivery_logs.models import DeliveryLog
from workers.tasks import send_email_reply_message
from .ai import get_ai_email_response

resend.api_key = settings.RESEND_API_KEY


def _log_email_response(candidate, message, status):
    DeliveryLog.objects.create(
        candidate=candidate,
        channel="email",
        recipient=candidate.email,
        message=message,
        status=status,
    )


def _save_response(candidate, status):
    candidate.status = status
    candidate.responded_via = "email"
    candidate.responded_at = timezone.now()


def process_email_reply(from_email, message):
    if not from_email or not message:
        return

    # extract email from "John Doe <john@gmail.com>" format
    if "<" in from_email and ">" in from_email:
        from_email = from_email.split("<")[1].replace(">", "").strip()

    try:
        candidate = Candidate.objects.get(email=from_email)
    except Candidate.DoesNotExist:
        return

    # add candidate message to conversation history
    candidate.email_conversation.append({
        "role": "user",
        "content": message,
    })

    # get AI response with full conversation history
    ai_response, status = get_ai_email_response(
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        job_description=candidate.job_description,
        conversation_history=candidate.email_conversation,
    )

    # add AI response to conversation history
    candidate.email_conversation.append({
        "role": "assistant",
        "content": ai_response,
    })

    if status == "interested":
        _save_response(candidate, "interested")
        _log_email_response(
            candidate,
            message=f"Candidate replied: '{message}' → AI detected: Interested",
            status="success",
        )

    elif status == "not_interested":
        _save_response(candidate, "not_interested")
        _log_email_response(
            candidate,
            message=f"Candidate replied: '{message}' → AI detected: Not Interested",
            status="success",
        )

    else:
        _log_email_response(
            candidate,
            message=f"Candidate replied: '{message}' → AI detected: Unclear",
            status="failed",
        )

    candidate.save()
    send_email_reply_message.delay(candidate.id, ai_response)


@api_view(["POST"])
def email_webhook(request):
    data = request.data
    print("FULL PAYLOAD:", data) 
    event_type = data.get("type", "")

    if event_type != "email.received":
        return Response({"status": "ignored"})

    email_data = data.get("data", {})
    email_id = email_data.get("email_id", "")
    from_email = email_data.get("from", "").strip()

    if not email_id:
        return Response({"status": "no email id"})

    if not from_email:
        return Response({"status": "no sender"})

    # fetch full email body from Resend
    try:
        email = resend.Emails.get(email_id)
        print("FETCHED EMAIL:", email)
        message = email.get("text", "").strip()
    except Exception as e:
        return Response({"status": f"failed to fetch email: {str(e)}"})

    if not message:
        return Response({"status": "empty message"})

    print("FINAL MESSAGE:", message)
    process_email_reply(from_email, message)

    return Response({"status": "received"})