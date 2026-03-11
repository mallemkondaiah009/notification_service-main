from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view

from candidate.models import Candidate, ConversationLog
from delivery_logs.models import DeliveryLog
from .call_templates import get_call_twiml, NO_INPUT_TWIML
from .ai import get_ai_response


def _log_call_response(candidate, message, status):
    DeliveryLog.objects.create(
        candidate=candidate,
        channel="call",
        recipient=candidate.phone,
        message=message,
        status=status,
    )


def _save_response(candidate, status):
    candidate.status = status
    candidate.responded_via = "call"
    candidate.responded_at = timezone.now()
    candidate.save()


def _build_twiml(text, action_url=None, gather=False):
    if gather:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" timeout="20" speechTimeout="auto" language="en-IN" actionOnEmptyResult="true">
        <Say voice="alice">{text}</Say>
    </Gather>
    <Say voice="alice">We did not receive your response. Goodbye.</Say>
</Response>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{text}</Say>
</Response>"""


@api_view(["GET", "POST"])
def call_twiml(request):
    candidate_id = request.query_params.get("candidate_id")

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except (Candidate.DoesNotExist, TypeError, ValueError):
        return HttpResponse(
            _build_twiml(
                "Hello, this is regarding your job application. "
                "Are you interested in this position? "
                "Please speak your response."
            ),
            content_type="text/xml",
        )

    # Store initial outbound call message
    ConversationLog.objects.create(
        candidate=candidate,
        channel="call",
        direction="outbound",
        sender="system",
        message=(
            f"Hello {candidate.full_name}, this is regarding your job application. "
            f"We are currently hiring for the position of {candidate.role_name}. "
            f"Are you interested in this position?"
        ),
    )

    twiml = get_call_twiml(
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        base_url=settings.BASE_URL,
    )
    return HttpResponse(twiml, content_type="text/xml")


@api_view(["POST"])
def call_response(request):
    speech = request.data.get("SpeechResult", "").strip()
    phone = request.data.get("To", "")

    try:
        candidate = Candidate.objects.get(phone=phone)
    except Candidate.DoesNotExist:
        return HttpResponse(
            _build_twiml("Candidate not found. Goodbye."),
            content_type="text/xml",
        )

    if not speech:
        _log_call_response(candidate, message="Candidate did not speak", status="failed")

        # Log no input from candidate
        ConversationLog.objects.create(
            candidate=candidate,
            channel="call",
            direction="inbound",
            sender="candidate",
            message="[No speech detected]",
        )
        return HttpResponse(NO_INPUT_TWIML, content_type="text/xml")

    # Store candidate's spoken response
    ConversationLog.objects.create(
        candidate=candidate,
        channel="call",
        direction="inbound",
        sender="candidate",
        message=speech,
    )

    ai_response, detected_status = get_ai_response(
        candidate_speech=speech,
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        job_description=candidate.job_description,
    )

    if detected_status == "interested":
        _save_response(candidate, "interested")
        _log_call_response(
            candidate,
            message=f"Candidate said: '{speech}' → AI detected: Interested",
            status="success",
        )

    elif detected_status == "not_interested":
        _save_response(candidate, "not_interested")
        _log_call_response(
            candidate,
            message=f"Candidate said: '{speech}' → AI detected: Not Interested",
            status="success",
        )

    else:
        _log_call_response(
            candidate,
            message=f"Candidate said: '{speech}' → AI detected: Unclear",
            status="failed",
        )

    # Store AI outbound reply for call
    ConversationLog.objects.create(
        candidate=candidate,
        channel="call",
        direction="outbound",
        sender="ai",
        message=ai_response,
        ai_detected_status=detected_status,
    )

    if detected_status in ("interested", "not_interested"):
        return HttpResponse(_build_twiml(ai_response), content_type="text/xml")

    return HttpResponse(
        _build_twiml(
            ai_response,
            action_url=f"{settings.BASE_URL}/call/response/",
            gather=True,
        ),
        content_type="text/xml",
    )