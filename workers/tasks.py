from celery import shared_task, group, chord
from celery.exceptions import Ignore
from django.utils import timezone

from candidate.models import Candidate
from whatsapp_service.services import send_whatsapp
from whatsapp_service.whatsapp_templates import send_initial_whatsapp
from email_service.services import send_email
from email_service.email_templates import candidate_email_template
from call_service.services import make_call
from shared.redis_client import redis_client
from shared.jd_parser import cache_jd_answers


@shared_task
def send_bulk_notifications(candidate_ids):
    batch_size = 50
    for i in range(0, len(candidate_ids), batch_size):
        batch = candidate_ids[i:i + batch_size]
        group(
            send_notification.s(candidate_id)
            for candidate_id in batch
        ).apply_async(countdown=i // batch_size * 2)


@shared_task
def send_notification(candidate_id):
    chord(
        group(
            send_whatsapp_notification.s(candidate_id),
            send_email_notification.s(candidate_id),
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

    send_initial_whatsapp(candidate)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def send_email_notification(self, candidate_id):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    if not candidate.email:
        return

    message = candidate_email_template(
        candidate.full_name,
        candidate.role_name,
        candidate.job_description,
    )
    send_email(candidate, message, is_initial=True)


@shared_task
def mark_candidate_notified(results, candidate_id):
    Candidate.objects.filter(id=candidate_id).update(
        status="sent",
        notification_sent_at=timezone.now(),
    )

    candidate = Candidate.objects.get(id=candidate_id)

    # Pre-cache JD answers before call starts
    cache_jd_answers(candidate.id, candidate.job_description, redis_client)

    check_and_call_candidate.apply_async(
        args=[candidate_id],
        countdown=20,
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def check_and_call_candidate(self, candidate_id):
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

    send_whatsapp(candidate, message, is_initial=False)