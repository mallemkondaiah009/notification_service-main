import redis
from django.conf import settings

redis_client = redis.Redis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
)


def safe_get(key):
    try:
        return redis_client.get(key)
    except redis.RedisError:
        return None


def safe_set(key, value, ex=None):
    try:
        redis_client.set(key, value, ex=ex)
    except redis.RedisError:
        pass


def safe_incr(key):
    try:
        redis_client.incr(key)
    except redis.RedisError:
        pass