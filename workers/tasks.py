"""
Celery tasks for notification delivery and call scheduling.

Changes from original:
  - Removed dead cache_jd_answers call (handler reads live from JD now)
  - Added raise Ignore() guard in check_and_call_candidate to prevent
    calling already-responded candidates on retry
  - Increased batch countdown spacing from 2s to 5s to avoid queue flooding
  - Added bulk notification dedup lock to prevent double-sending
  - Added structured logging on key tasks
"""
import logging

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

logger = logging.getLogger("tasks")


# ── Bulk notification entry point ─────────────────────────────────────

@shared_task
def send_bulk_notifications(candidate_ids, campaign_id=None):
    """
    Fans out notifications for a list of candidate IDs in batches of 50.
    Uses a Redis lock to prevent double-sending if triggered twice.

    Args:
        candidate_ids: list of candidate PKs
        campaign_id: optional identifier for dedup lock (use a UUID or timestamp)
    """
    # ── Dedup lock ────────────────────────────────────────────────────
    if campaign_id:
        lock_key = f"bulk_notify_lock:{campaign_id}"
        if not redis_client.set(lock_key, "1", nx=True, ex=3600):
            logger.warning(f"[TASKS] Bulk notify already running — campaign_id={campaign_id}")
            raise Ignore()

    batch_size = 50
    for i in range(0, len(candidate_ids), batch_size):
        batch = candidate_ids[i : i + batch_size]
        batch_number = i // batch_size

        group(
            send_notification.s(candidate_id)
            for candidate_id in batch
        ).apply_async(countdown=batch_number * 5)  # 5s between batches (was 2s)

    logger.info(
        f"[TASKS] Bulk notify dispatched — "
        f"total={len(candidate_ids)} batches={len(candidate_ids) // batch_size + 1}"
    )


# ── Per-candidate notification ────────────────────────────────────────

@shared_task
def send_notification(candidate_id):
    """
    Sends WhatsApp + Email in parallel via chord.
    Calls mark_candidate_notified when both complete.
    """
    chord(
        group(
            send_whatsapp_notification.s(candidate_id),
            send_email_notification.s(candidate_id),
        ),
        mark_candidate_notified.s(candidate_id),
    ).apply_async()


# ── WhatsApp notification ─────────────────────────────────────────────

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

    logger.info(f"[TASKS] Sending WhatsApp — candidate={candidate_id}")
    send_initial_whatsapp(candidate)


# ── Email notification ────────────────────────────────────────────────

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
        logger.info(f"[TASKS] Skipping email — no address — candidate={candidate_id}")
        return

    logger.info(f"[TASKS] Sending email — candidate={candidate_id}")
    message = candidate_email_template(
        candidate.full_name,
        candidate.role_name,
        candidate.job_description,
    )
    send_email(candidate, message, is_initial=True)


# ── Post-notification: mark sent + schedule call ─────────────────────

@shared_task
def mark_candidate_notified(results, candidate_id):
    """
    Chord callback — runs after both WhatsApp and Email complete.
    results = [None, None] (return values of the two notification tasks)
    """
    Candidate.objects.filter(id=candidate_id).update(
        status="sent",
        notification_sent_at=timezone.now(),
    )

    logger.info(f"[TASKS] Candidate marked sent — candidate={candidate_id}")

    # Schedule call 20 seconds after notifications are sent.
    # No JD pre-caching needed — handler reads live from JD.
    check_and_call_candidate.apply_async(
        args=[candidate_id],
        countdown=20,
    )


# ── Outbound call ─────────────────────────────────────────────────────

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def check_and_call_candidate(self, candidate_id):
    """
    Makes the outbound call only if candidate is still in 'sent' status.

    Guard on every attempt (including retries):
    - If candidate already responded via WhatsApp/email/previous call,
      skip the call entirely.
    """
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    # ── Status guard — checked on every attempt including retries ────
    if candidate.status != "sent":
        logger.info(
            f"[TASKS] Skipping call — candidate already responded "
            f"status={candidate.status} candidate={candidate_id}"
        )
        raise Ignore()

    logger.info(f"[TASKS] Making call — candidate={candidate_id}")
    make_call(candidate)


# ── Periodic log buffer flush ─────────────────────────────────────────

@shared_task
def flush_log_buffers():
    """
    Flushes buffered ConversationLog and DeliveryLog entries to DB.
    Runs every 30 seconds via Celery beat.
    Flushes ALL channels — call, whatsapp, email — in one task.

    Add to settings.py:
        CELERY_BEAT_SCHEDULE = {
            "flush-log-buffers": {
                "task": "api.tasks.flush_log_buffers",
                "schedule": 30.0,
            },
        }
    """
    from shared.cache import flush_log_buffers as _flush
    conv_count, delv_count = _flush()   # flushes call + whatsapp + email
    logger.info(f"[TASKS] Log flush — conv={conv_count} delivery={delv_count}")

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

    logger.info(f"[TASKS] Sending WhatsApp reply — candidate={candidate_id}")
    send_whatsapp(candidate, message, is_initial=False)