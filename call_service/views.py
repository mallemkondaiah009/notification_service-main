"""
Twilio webhook views for call_service.
No caching — pure DB reads and writes.
"""
import html
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from twilio.request_validator import RequestValidator

from candidate.models import Candidate, ConversationLog
from delivery_logs.models import DeliveryLog
from .call_templates import get_call_twiml, NO_INPUT_TWIML, VOICE, LANGUAGE
from .handler import handle_call_speech

logger = logging.getLogger("call_service")


# ── Twilio request validator ──────────────────────────────────────────

def _validate_twilio_request(request) -> bool:
    """
    Validates the request actually came from Twilio.
    Skipped in DEBUG mode for local testing.
    """
    if settings.DEBUG:
        return True
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
    url = request.build_absolute_uri()
    post_data = request.data if hasattr(request, "data") else {}
    return validator.validate(url, post_data, signature)


# ── TwiML builders ────────────────────────────────────────────────────

def _build_twiml(text: str, action_url: str = None, gather: bool = False) -> str:
    if gather:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" timeout="20" speechTimeout="auto" language="{LANGUAGE}">
        <Say voice="{VOICE}">{text}</Say>
    </Gather>
    <Say voice="{VOICE}">We did not receive your response. Goodbye.</Say>
</Response>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{VOICE}">{text}</Say>
</Response>"""


# ── Call response handler ─────────────────────────────────────────────

class CallResponseHandler:

    def save_candidate_status(self, candidate, status: str):
        """Write status change directly to DB."""
        candidate.status = status
        candidate.responded_via = "call"
        candidate.responded_at = timezone.now()
        candidate.save()

    def log_delivery(self, candidate, message: str, status: str):
        """Write delivery log directly to DB."""
        try:
            DeliveryLog.objects.create(
                candidate=candidate,
                channel="call",
                recipient=candidate.phone,
                message=message,
                status=status,
            )
        except Exception as e:
            logger.warning(f"[CALL] DeliveryLog write failed: {e}")

    def log_conversation(
        self,
        candidate,
        direction: str,
        sender: str,
        message: str,
        ai_detected_status: str = None,
    ):
        """Write conversation log directly to DB — immediately visible."""
        try:
            kwargs = dict(
                candidate=candidate,
                channel="call",
                direction=direction,
                sender=sender,
                message=message,
            )
            if ai_detected_status:
                kwargs["ai_detected_status"] = ai_detected_status
            ConversationLog.objects.create(**kwargs)
        except Exception as e:
            logger.warning(f"[CALL] ConversationLog write failed: {e}")

    def process(self, candidate, speech: str) -> HttpResponse:
        spoken_reply, detected_status, source = handle_call_speech(candidate, speech)

        # ── Duplicate request ─────────────────────────────────────────
        if detected_status == "duplicate":
            return HttpResponse(
                _build_twiml("Please wait."),
                content_type="text/xml",
            )

        logger.info(
            "[CALL] turn processed",
            extra={
                "candidate_id": candidate.id,
                "source": source,
                "status": detected_status,
                "speech_len": len(speech),
            },
        )

        # ── Save final status ─────────────────────────────────────────
        if detected_status == "interested":
            self.save_candidate_status(candidate, "interested")
            self.log_delivery(candidate, f"[{source.upper()}] Candidate interested", "success")

        elif detected_status == "not_interested":
            self.save_candidate_status(candidate, "not_interested")
            self.log_delivery(candidate, f"[{source.upper()}] Candidate not interested", "success")

        else:
            self.log_delivery(candidate, f"[{source.upper()}] Speech: '{speech}' → unclear", "failed")

        # ── Log outbound reply ────────────────────────────────────────
        self.log_conversation(
            candidate=candidate,
            direction="outbound",
            sender="system" if source == "jd" else "ai",
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


_handler = CallResponseHandler()


# ── Views ─────────────────────────────────────────────────────────────

@api_view(["GET", "POST"])
def call_twiml(request):
    try:
        if not _validate_twilio_request(request):
            logger.warning("[CALL] Invalid Twilio signature on /call/twiml/")
            return HttpResponse(status=403)

        candidate_id = request.query_params.get("candidate_id")

        try:
            candidate = Candidate.objects.get(id=candidate_id)
        except (Candidate.DoesNotExist, TypeError, ValueError):
            logger.warning(f"[CALL] Candidate not found — id={candidate_id}")
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

    except Exception as e:
        logger.error(f"[CALL] Unhandled exception in call_twiml: {e}", exc_info=True)
        return HttpResponse(
            _build_twiml(
                "Hello, this is regarding your job application. "
                "We are experiencing a technical issue. "
                "Our team will call you back shortly. Goodbye."
            ),
            content_type="text/xml",
        )


@api_view(["POST"])
def call_response(request):
    try:
        if not _validate_twilio_request(request):
            logger.warning("[CALL] Invalid Twilio signature on /call/response/")
            return HttpResponse(status=403)

        speech = request.data.get("SpeechResult", "").strip()

        # Use 'From' — candidate's number, not 'To' (our Twilio number)
        phone = request.data.get("To", "").strip()

        try:
            candidate = Candidate.objects.get(phone=phone)
        except Candidate.DoesNotExist:
            logger.warning(f"[CALL] Candidate not found for phone={phone}")
            return HttpResponse(
                _build_twiml("Candidate not found. Goodbye."),
                content_type="text/xml",
            )

        # ── No speech detected ────────────────────────────────────────
        if not speech:
            DeliveryLog.objects.create(
                candidate=candidate,
                channel="call",
                recipient=candidate.phone,
                message="Candidate did not speak",
                status="failed",
            )
            ConversationLog.objects.create(
                candidate=candidate,
                channel="call",
                direction="inbound",
                sender="candidate",
                message="[No speech detected]",
            )
            return HttpResponse(NO_INPUT_TWIML, content_type="text/xml")

        # ── Log inbound speech ────────────────────────────────────────
        ConversationLog.objects.create(
            candidate=candidate,
            channel="call",
            direction="inbound",
            sender="candidate",
            message=speech,
        )

        return _handler.process(candidate, speech)

    except Exception as e:
        logger.error(f"[CALL] Unhandled exception in call_response: {e}", exc_info=True)
        return HttpResponse(
            _build_twiml(
                "I'm sorry, we are experiencing a technical issue. "
                "Our team will call you back shortly. Goodbye."
            ),
            content_type="text/xml",
        )