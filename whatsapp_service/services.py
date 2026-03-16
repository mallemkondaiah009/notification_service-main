from twilio.rest import Client
from django.conf import settings

from delivery_logs.models import DeliveryLog
from candidate.models import ConversationLog


def send_text_message(to_phone, message):
    """Raw Twilio call — single entry point for all outbound WhatsApp sends."""
    try:
        client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
        )
        client.messages.create(
            body=message,
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{to_phone}",
        )
    except Exception as e:
        raise Exception(f"Failed to send WhatsApp message: {str(e)}")


def send_whatsapp(candidate, message, is_initial=False):
    """Send with full delivery + conversation logging."""
    try:
        send_text_message(candidate.phone, message)

        DeliveryLog.objects.create(
            candidate=candidate,
            channel="whatsapp",
            recipient=candidate.phone,
            message=message,
            status="success",
        )

        if is_initial:
            ConversationLog.objects.create(
                candidate=candidate,
                channel="whatsapp",
                direction="outbound",
                sender="system",
                message=message,
            )

    except Exception as e:
        DeliveryLog.objects.create(
            candidate=candidate,
            channel="whatsapp",
            recipient=candidate.phone,
            message=message,
            status="failed",
            error_message=str(e),
        )
        raise