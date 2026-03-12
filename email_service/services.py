from django.core.mail import send_mail
from django.conf import settings

from delivery_logs.models import DeliveryLog
from candidate.models import ConversationLog


def send_email(candidate, message, subject="Job Opportunity - Action Required", is_initial=False):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[candidate.email],
            fail_silently=False,
        )

        DeliveryLog.objects.create(
            candidate=candidate,
            channel="email",
            recipient=candidate.email,
            message=message,
            status="success",
        )

        if is_initial:
            ConversationLog.objects.create(
                candidate=candidate,
                channel="email",
                direction="outbound",
                sender="system",
                message=message,
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