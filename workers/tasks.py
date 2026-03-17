"""
Celery tasks — WhatsApp service only.

Celery workers are sync threads. asyncio.run() is the correct bridge
into async service functions — it creates a fresh event loop per task,
runs the coroutine, then tears it down cleanly.
"""
import asyncio
import logging

import redis
from celery import shared_task
from celery.exceptions import Ignore
from django.conf import settings
from django.utils import timezone

from candidate.models import Candidate
from whatsapp_service.services import send_text_message
from whatsapp_service.whatsapp_templates import send_initial_whatsapp

logger = logging.getLogger("tasks.whatsapp")

# Sync Redis — only for Celery-internal dedup locks
_redis_sync = redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)


# ── Bulk kick-off ──────────────────────────────────────────────────────

@shared_task
def send_bulk_whatsapp_notifications(candidate_ids: list[int], campaign_id: str | None = None):
    """
    Fans out per-candidate WhatsApp notifications in batches of 50.
    Dedup lock prevents double-fire on the same campaign_id.
    """
    if campaign_id:
        lock_key = f"bulk_wa_lock:{campaign_id}"
        if not _redis_sync.set(lock_key, "1", nx=True, ex=3600):
            logger.warning("[TASKS] Already running — campaign=%s", campaign_id)
            raise Ignore()

    from celery import group

    batch_size = 50
    for i in range(0, len(candidate_ids), batch_size):
        batch = candidate_ids[i : i + batch_size]
        group(
            send_whatsapp_notification.s(cid) for cid in batch
        ).apply_async(countdown=(i // batch_size) * 5)

    logger.info("[TASKS] Bulk dispatched — total=%d", len(candidate_ids))


# ── Per-candidate initial notification ────────────────────────────────

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def send_whatsapp_notification(self, candidate_id: int):
    """
    Sends the initial WhatsApp menu and marks candidate as 'sent'.
    """
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    logger.info("[TASKS] Sending initial WhatsApp — candidate=%d", candidate_id)
    asyncio.run(send_initial_whatsapp(candidate))

    Candidate.objects.filter(id=candidate_id).update(
        status="sent",
        notification_sent_at=timezone.now(),
    )
    logger.info("[TASKS] Marked sent — candidate=%d", candidate_id)


# ── Reply message (fired from async webhook via .delay()) ─────────────

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
)
def send_whatsapp_reply_task(self, candidate_id: int, message: str):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    logger.info("[TASKS] Sending reply — candidate=%d", candidate_id)
    asyncio.run(send_text_message(candidate.phone, message))