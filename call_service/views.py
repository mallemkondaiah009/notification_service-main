import html
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view

from candidate.models import Candidate, ConversationLog
from delivery_logs.models import DeliveryLog
from .call_templates import get_call_twiml, NO_INPUT_TWIML
from .handler import handle_call_speech

logger = logging.getLogger("call_service")


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
    <Gather input="speech" action="{action_url}" method="POST" timeout="20" speechTimeout="auto" language="en-IN">
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
    phone = request.data.get("To", "").strip()

    try:
        candidate = Candidate.objects.get(phone=phone)
    except Candidate.DoesNotExist:
        logger.warning(f"[CALL] Candidate not found for phone={phone}")
        return HttpResponse(
            _build_twiml("Candidate not found. Goodbye."),
            content_type="text/xml",
        )

    if not speech:
        _log_call_response(candidate, "Candidate did not speak", "failed")
        ConversationLog.objects.create(
            candidate=candidate,
            channel="call",
            direction="inbound",
            sender="candidate",
            message="[No speech detected]",
        )
        return HttpResponse(NO_INPUT_TWIML, content_type="text/xml")

    ConversationLog.objects.create(
        candidate=candidate,
        channel="call",
        direction="inbound",
        sender="candidate",
        message=speech,
    )

    # ── Handle speech ─────────────────────────────────────────────────
    spoken_reply, detected_status, source = handle_call_speech(candidate, speech)

    # ── Ignore duplicate Twilio requests ─────────────────────────────
    if detected_status == "duplicate":
        return HttpResponse(
            _build_twiml("Please wait."),
            content_type="text/xml",
        )

    # ── Save status if final ──────────────────────────────────────────
    if detected_status == "interested":
        _save_response(candidate, "interested")
        _log_call_response(candidate, f"[{source.upper()}] Candidate interested", "success")

    elif detected_status == "not_interested":
        _save_response(candidate, "not_interested")
        _log_call_response(candidate, f"[{source.upper()}] Candidate not interested", "success")

    else:
        _log_call_response(candidate, f"[{source.upper()}] Speech: '{speech}' → unclear", "failed")

    ConversationLog.objects.create(
    candidate=candidate,
    channel="call",
    direction="outbound",
    sender="system" if source == "jd" else "ai",  # ← correct
    message=spoken_reply,
    ai_detected_status=detected_status,
)

    safe_reply = html.escape(spoken_reply)

    if detected_status in ("interested", "not_interested"):
        return HttpResponse(_build_twiml(safe_reply), content_type="text/xml")

    return HttpResponse(
        _build_twiml(
            safe_reply,
            action_url=f"{settings.BASE_URL}/call/response/",
            gather=True,
        ),
        content_type="text/xml",
    )