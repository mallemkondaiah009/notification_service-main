import json
import logging

from django.db import models
from django.utils import timezone

from shared.redis_client import redis_context

logger = logging.getLogger("whatsapp.models")

CANDIDATE_CACHE_TTL = 60 * 60 * 24  # 24 hours


class JobDescription(models.Model):
    title      = models.CharField(max_length=200)
    content    = models.TextField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["title"])]

    def __str__(self):
        return self.title


class Candidate(models.Model):

    STATUS_CHOICES = (
        ("pending",        "Pending"),
        ("sent",           "Notification Sent"),
        ("interested",     "Interested"),
        ("not_interested", "Not Interested"),
    )

    RESPONDED_VIA_CHOICES = (
        ("email",    "Email"),
        ("whatsapp", "WhatsApp"),
        ("call",     "Call"),
    )

    full_name    = models.CharField(max_length=200)
    email        = models.EmailField(blank=True)
    phone        = models.CharField(max_length=20)
    role_name    = models.CharField(max_length=200)
    job          = models.ForeignKey(
        JobDescription,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="candidates",
    )

    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    responded_via        = models.CharField(max_length=20, choices=RESPONDED_VIA_CHOICES, null=True, blank=True)
    responded_at         = models.DateTimeField(null=True, blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["phone"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.full_name

    @property
    def job_description(self) -> str:
        """Backward compat — call_service uses candidate.job_description."""
        return self.job.content

    # ── Cache helpers ──────────────────────────────────────────────────

    @classmethod
    def _cache_key(cls, phone: str) -> str:
        return f"candidate_phone:{phone}"

    @classmethod
    async def _aset_cache(cls, candidate: "Candidate") -> None:
        try:
            await redis_context.set(
                cls._cache_key(candidate.phone),
                json.dumps({
                    "id":            candidate.id,
                    "full_name":     candidate.full_name,
                    "phone":         candidate.phone,
                    "email":         candidate.email,
                    "role_name":     candidate.role_name,
                    "status":        candidate.status,
                    "responded_via": candidate.responded_via,
                    "job_id":        candidate.job.id,
                    "job_title":     candidate.job.title,
                    "job_content":   candidate.job.content,
                }),
                ex=CANDIDATE_CACHE_TTL,
            )
        except Exception as exc:
            logger.error(
                "[MODELS] _aset_cache failed — phone=%s error=%s",
                candidate.phone, exc,
            )

    @classmethod
    async def ainvalidate_phone_cache(cls, phone: str) -> None:
        try:
            await redis_context.delete(cls._cache_key(phone))
        except Exception as exc:
            logger.error(
                "[MODELS] ainvalidate_phone_cache failed — phone=%s error=%s",
                phone, exc,
            )

    # ── Async fetch ────────────────────────────────────────────────────

    @classmethod
    async def aget_by_phone(cls, phone: str) -> "Candidate":
        """
        Fetch candidate by phone.
        Redis cache first → DB fallback → re-cache on DB hit.
        Raises DoesNotExist if not found.
        """
        cache_key = cls._cache_key(phone)

        # Try cache first
        try:
            cached = await redis_context.get(cache_key)
            if cached:
                data      = json.loads(cached)
                job       = JobDescription(
                    id      = data["job_id"],
                    title   = data["job_title"],
                    content = data["job_content"],
                )
                candidate             = cls()
                candidate.id          = data["id"]
                candidate.full_name   = data["full_name"]
                candidate.phone       = data["phone"]
                candidate.email       = data["email"]
                candidate.role_name   = data["role_name"]
                candidate.status      = data["status"]
                candidate.responded_via = data["responded_via"]
                candidate.job         = job
                candidate.job_id      = data["job_id"]
                return candidate
        except Exception as exc:
            logger.warning(
                "[MODELS] Cache read failed — phone=%s error=%s falling back to DB",
                phone, exc,
            )

        # DB fallback — psycopg3 async, no thread pool
        candidate = await cls.objects.select_related("job").aget(phone=phone)
        await cls._aset_cache(candidate)
        return candidate

    @classmethod
    async def aget_by_phone_or_none(cls, phone: str) -> "Candidate | None":
        try:
            return await cls.aget_by_phone(phone)
        except cls.DoesNotExist:
            return None

    @classmethod
    async def aget_fresh(cls, candidate_id: int) -> "Candidate | None":
        """Fetch directly from DB — bypasses cache entirely."""
        try:
            return await cls.objects.select_related("job").aget(id=candidate_id)
        except cls.DoesNotExist:
            return None

    # ── Async state mutations ──────────────────────────────────────────

    async def amark_response(self, status: str, via: str) -> None:
        self.status        = status
        self.responded_via = via
        self.responded_at  = timezone.now()
        await self.asave(update_fields=["status", "responded_via", "responded_at"])
        await self.ainvalidate_phone_cache(self.phone)

    async def amark_sent(self) -> None:
        self.status               = "sent"
        self.notification_sent_at = timezone.now()
        await self.asave(update_fields=["status", "notification_sent_at"])
        await self.ainvalidate_phone_cache(self.phone)

    async def ais_already_decided(self) -> bool:
        return self.status in ("interested", "not_interested")


class ConversationLog(models.Model):

    CHANNEL_CHOICES   = [("whatsapp", "WhatsApp"), ("call", "Call")]
    DIRECTION_CHOICES = [("outbound", "Outbound"), ("inbound", "Inbound")]
    SENDER_CHOICES    = [("system", "System"), ("ai", "AI"), ("candidate", "Candidate")]

    candidate          = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="conversation_logs")
    channel            = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    direction          = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    sender             = models.CharField(max_length=20, choices=SENDER_CHOICES)
    message            = models.TextField()
    ai_detected_status = models.CharField(max_length=20, null=True, blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.channel}] {self.candidate} | {self.sender} | {self.created_at}"

    @classmethod
    async def alog(
        cls,
        candidate: "Candidate",
        channel: str,
        direction: str,
        sender: str,
        message: str,
        ai_detected_status: str | None = None,
    ) -> "ConversationLog | None":
        """Never raises — logging failure must never crash the webhook."""
        try:
            return await cls.objects.acreate(
                candidate=candidate,
                channel=channel,
                direction=direction,
                sender=sender,
                message=message,
                ai_detected_status=ai_detected_status,
            )
        except Exception as exc:
            logger.error("[MODELS] ConversationLog.alog failed — %s", exc)
            return None

    @classmethod
    async def aget_recent(
        cls,
        candidate: "Candidate",
        channel: str = "whatsapp",
        limit: int = 5,
    ) -> list[dict]:
        """
        Returns last N messages as plain dicts for AI history.
        psycopg3 async — no sync_to_async needed.
        """
        try:
            result = []
            async for entry in (
                cls.objects
                .filter(candidate=candidate, channel=channel)
                .order_by("-created_at")
                .values("sender", "message", "direction")[:limit]
            ):
                result.append(entry)
            result.reverse()
            return result
        except Exception as exc:
            logger.error("[MODELS] aget_recent failed — %s", exc)
            return []

    @classmethod
    async def acount_today(
        cls,
        candidate: "Candidate",
        channel: str = "whatsapp",
    ) -> int:
        """Count messages today — used for rate limiting."""
        try:
            today = timezone.now().date()
            return await cls.objects.filter(
                candidate=candidate,
                channel=channel,
                created_at__date=today,
            ).acount()
        except Exception:
            return 0
