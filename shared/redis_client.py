import redis
import redis.asyncio as aioredis
from django.conf import settings

# Async client — views, quick_replies, jd_parser
redis_client = aioredis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
)

# Sync client — Celery tasks and call_service only
redis_client_sync = redis.Redis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
)

# ── Async helpers ──────────────────────────────────────────────────────

async def safe_get(key: str):
    try:
        return await redis_client.get(key)
    except Exception:
        return None

async def safe_set(key: str, value, ex: int | None = None):
    try:
        await redis_client.set(key, value, ex=ex)
    except Exception:
        pass

async def safe_delete(key: str):
    try:
        await redis_client.delete(key)
    except Exception:
        pass

# ── Sync helpers — call_service and Celery tasks ───────────────────────

def safe_incr(key: str) -> None:
    try:
        redis_client_sync.incr(key)
    except Exception:
        pass

def safe_get_sync(key: str):
    try:
        return redis_client_sync.get(key)
    except Exception:
        return None

def safe_set_sync(key: str, value, ex: int | None = None) -> None:
    try:
        redis_client_sync.set(key, value, ex=ex)
    except Exception:
        pass