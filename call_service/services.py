from django.conf import settings
from twilio.rest import Client
from urllib.parse import urlencode

from delivery_logs.models import DeliveryLog


def make_call(candidate):
    try:
        client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
        )

        params = urlencode({"candidate_id": candidate.id})

        call = client.calls.create(
            to=candidate.phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=f"{settings.BASE_URL}/call/twiml/?{params}",
        )

        DeliveryLog.objects.create(
            candidate=candidate,
            channel="call",
            recipient=candidate.phone,
            message="Automated recruitment call initiated",
            status="success",
        )

        return call.sid

    except Exception as e:
        DeliveryLog.objects.create(
            candidate=candidate,
            channel="call",
            recipient=candidate.phone,
            message="Automated recruitment call failed",
            status="failed",
            error_message=str(e),
        )
        raise