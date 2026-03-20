import asyncio
import logging

import redis
from celery import shared_task, group
from celery.exceptions import Ignore, SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from candidate.models import Candidate
from whatsapp_service.services import send_text_message
from whatsapp_service.whatsapp_templates import send_initial_whatsapp
from shared.jd_parser import cache_jd_answers

logger = logging.getLogger("tasks.whatsapp")

_redis_sync = redis.Redis.from_url(
    settings.REDIS_LOCKS_URL,
    decode_responses=True,
)


@shared_task
def send_bulk_whatsapp_notifications(
    candidate_ids: list[int],
    campaign_id: str | None = None,
):
    if campaign_id:
        lock_key = f"bulk_wa_lock:{campaign_id}"
        if not _redis_sync.set(lock_key, "1", nx=True, ex=3600):
            logger.warning("[TASKS] Already running — campaign=%s", campaign_id)
            raise Ignore()

    batch_size = 50
    for i in range(0, len(candidate_ids), batch_size):
        batch = candidate_ids[i : i + batch_size]
        group(
            send_whatsapp_notification.s(cid) for cid in batch
        ).apply_async(countdown=(i // batch_size) * 5)

    logger.info(
        "[TASKS] Bulk dispatched — total=%d campaign=%s",
        len(candidate_ids), campaign_id,
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
    soft_time_limit=10,
    time_limit=15,
)
def send_whatsapp_notification(self, candidate_id: int):
    try:
        candidate = Candidate.objects.select_related("job").get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    # if candidate.status != "pending":
    #     logger.info(
    #         "[TASKS] Skipping — status=%s candidate=%d",
    #         candidate.status, candidate_id,
    #     )
    #     raise Ignore()

    try:
        logger.info("[TASKS] Sending initial WhatsApp — candidate=%d", candidate_id)
        asyncio.run(send_initial_whatsapp(candidate))

        Candidate.objects.filter(id=candidate_id).update(
            status="sent",
            notification_sent_at=timezone.now(),
        )
        logger.info("[TASKS] Marked sent — candidate=%d", candidate_id)

        asyncio.run(Candidate.ainvalidate_phone_cache(candidate.phone))

        asyncio.run(cache_jd_answers(candidate.job.id, candidate.job.content))
        logger.info(
            "[TASKS] JD cache warmed — jd_id=%d candidate=%d",
            candidate.job.id, candidate_id,
        )

    except SoftTimeLimitExceeded:
        logger.error("[TASKS] Soft time limit — candidate=%d", candidate_id)
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 5},
    soft_time_limit=10,
    time_limit=15,
)
def send_whatsapp_reply_task(self, candidate_id: int, message: str):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise Ignore()

    if not candidate.phone:
        logger.warning("[TASKS] No phone — candidate=%d", candidate_id)
        raise Ignore()

    try:
        logger.info("[TASKS] Sending reply — candidate=%d", candidate_id)
        asyncio.run(send_text_message(candidate.phone, message))

    except SoftTimeLimitExceeded:
        logger.error("[TASKS] Soft time limit — candidate=%d", candidate_id)
        raise