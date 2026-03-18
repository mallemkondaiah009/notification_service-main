import redis
import redis.asyncio as aioredis
from django.conf import settings

# ── Async — views, quick_replies, jd_parser ───────────────────────────
redis_context = aioredis.from_url(
    settings.REDIS_CONTEXT_URL,
    decode_responses=True,
)

# Backward compat alias — call_service imports redis_client
redis_client = redis_context

# ── Sync — Celery tasks only ───────────────────────────────────────────
redis_celery_sync = redis.Redis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
)

redis_locks_sync = redis.Redis.from_url(
    settings.REDIS_LOCKS_URL,
    decode_responses=True,
)

# ── Async helpers ──────────────────────────────────────────────────────

async def safe_get(key: str):
    try:
        return await redis_context.get(key)
    except Exception:
        return None

async def safe_set(key: str, value, ex: int | None = None):
    try:
        await redis_context.set(key, value, ex=ex)
    except Exception:
        pass

async def safe_delete(key: str):
    try:
        await redis_context.delete(key)
    except Exception:
        pass

# ── Sync helpers — call_service ────────────────────────────────────────

def safe_incr(key: str) -> None:
    try:
        redis_celery_sync.incr(key)
    except Exception:
        pass

def safe_get_sync(key: str):
    try:
        return redis_celery_sync.get(key)
    except Exception:
        return None

def safe_set_sync(key: str, value, ex: int | None = None) -> None:
    try:
        redis_celery_sync.set(key, value, ex=ex)
    except Exception:
        pass