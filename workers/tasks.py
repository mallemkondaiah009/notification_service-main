from celery import shared_task, group, chord
from celery.exceptions import Ignore
from django.utils import timezone

from candidate.models import Candidate
from whatsapp_service.services import send_whatsapp
from whatsapp_service.whatsapp_templates import candidate_whatsapp_template
from call_service.services import make_call


@shared_task
def send_bulk_notifications(candidate_ids):
    """
    Entry point — fires send_notification in parallel for each candidate.
    POST body: { "candidate_ids": [1, 2, 3] }
    """
    job = group(
        send_notification.s(candidate_id)
        for candidate_id in candidate_ids
    )
    job.apply_async()


@shared_task
def send_notification(candidate_id):
    """
    Per-candidate flow:
      1. Send WhatsApp notification
      2. On success → mark candidate as notified
      3. After 20 seconds → check if still unresponded → make call
    """
    chord(
        group(
            send_whatsapp_notification.s(candidate_id),
        ),
        mark_candidate_notified.s(candidate_id),
    ).apply_async()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def send_whatsapp_notification(self, candidate_id):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    message = candidate_whatsapp_template(
        candidate.full_name,
        candidate.role_name,
    )
    # is_initial=True logs this as first outbound message
    send_whatsapp(candidate, message, is_initial=True)


@shared_task
def mark_candidate_notified(results, candidate_id):
    Candidate.objects.filter(id=candidate_id).update(
        status="sent",
        notification_sent_at=timezone.now(),
    )
    check_and_call_candidate.apply_async(
        args=[candidate_id],
        countdown=20,  # ← 20 seconds for testing
    )


@shared_task
def check_and_call_candidate(candidate_id):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    if candidate.status == "sent":
        make_call(candidate)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def send_whatsapp_reply_message(self, candidate_id, message):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    # is_initial=False — reply already logged in webhook view
    send_whatsapp(candidate, message, is_initial=False)