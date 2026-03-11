from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from candidate.models import Candidate, ConversationLog
from delivery_logs.models import DeliveryLog
from workers.tasks import send_whatsapp_reply_message
from .ai import get_ai_whatsapp_response


def _log_whatsapp_response(candidate, message, status):
    DeliveryLog.objects.create(
        candidate=candidate,
        channel="whatsapp",
        recipient=candidate.phone,
        message=message,
        status=status,
    )


def _save_response(candidate, status):
    candidate.status = status
    candidate.responded_via = "whatsapp"
    candidate.responded_at = timezone.now()
    candidate.save()


@api_view(["POST"])
def whatsapp_webhook(request):
    phone = request.data.get("From", "").replace("whatsapp:", "")
    message = request.data.get("Body", "").strip()

    try:
        candidate = Candidate.objects.get(phone=phone)
    except Candidate.DoesNotExist:
        return Response({"status": "candidate not found"})

    if not message:
        return Response({"status": "empty message"})

    # Store candidate's inbound message
    ConversationLog.objects.create(
        candidate=candidate,
        channel="whatsapp",
        direction="inbound",
        sender="candidate",
        message=message,
    )

    ai_response, detected_status = get_ai_whatsapp_response(
        candidate_message=message,
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        job_description=candidate.job_description,
    )

    if detected_status == "interested":
        _save_response(candidate, "interested")
        _log_whatsapp_response(
            candidate,
            message=f"Candidate said: '{message}' → AI detected: Interested",
            status="success",
        )

    elif detected_status == "not_interested":
        _save_response(candidate, "not_interested")
        _log_whatsapp_response(
            candidate,
            message=f"Candidate said: '{message}' → AI detected: Not Interested",
            status="success",
        )

    else:
        _log_whatsapp_response(
            candidate,
            message=f"Candidate said: '{message}' → AI detected: Unclear",
            status="failed",
        )

    # Store AI outbound reply
    ConversationLog.objects.create(
        candidate=candidate,
        channel="whatsapp",
        direction="outbound",
        sender="ai",
        message=ai_response,
        ai_detected_status=detected_status,
    )

    send_whatsapp_reply_message.delay(candidate.id, ai_response)

    return Response({"status": "received"})