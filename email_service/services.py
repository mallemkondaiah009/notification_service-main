import resend
from django.conf import settings

from delivery_logs.models import DeliveryLog

resend.api_key = settings.RESEND_API_KEY


def send_email(candidate, message, subject="Job Opportunity"):
    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": candidate.email,
            "subject": subject,
            "text": message,
        })

        DeliveryLog.objects.create(
            candidate=candidate,
            channel="email",
            recipient=candidate.email,
            message=message,
            status="success",
        )

    except Exception as e:
        DeliveryLog.objects.create(
            candidate=candidate,
            channel="email",
            recipient=candidate.email,
            message=message,
            status="failed",
            error_message=str(e),
        )
        raise