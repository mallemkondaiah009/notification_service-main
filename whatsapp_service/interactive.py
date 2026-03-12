from twilio.rest import Client
from django.conf import settings

from delivery_logs.models import DeliveryLog


def send_text_message(to_phone, message):
    """Send a plain text WhatsApp message via Twilio."""
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