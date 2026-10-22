import redis
import redis.asyncio as aioredis
from django.conf import settings

# ── Async clients with connection pools ───────────────────────────────

redis_context = aioredis.from_url(
    settings.REDIS_CONTEXT_URL,
    decode_responses=True,
    max_connections=50,        # ← pool size for 500 concurrent requests
    socket_connect_timeout=2,
    socket_timeout=2,
    retry_on_timeout=True,
)

redis_client = redis_context

# ── Sync clients ───────────────────────────────────────────────────────

redis_celery_sync = redis.Redis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
    max_connections=20,
)

redis_locks_sync = redis.Redis.from_url(
    settings.REDIS_LOCKS_URL,
    decode_responses=True,
    max_connections=10,
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

# ── Sync helpers ───────────────────────────────────────────────────────

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