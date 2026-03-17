import logging

from asgiref.sync import sync_to_async
from django.db import models
from django.utils import timezone

logger = logging.getLogger("whatsapp.models")


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

    full_name       = models.CharField(max_length=200)
    email           = models.EmailField(blank=True)
    phone           = models.CharField(max_length=20)
    role_name       = models.CharField(max_length=200)
    job_description = models.TextField()

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

    # ── Async fetch helpers ────────────────────────────────────────────

    @classmethod
    async def aget_by_phone(cls, phone: str) -> "Candidate":
        """Fetch by phone — raises DoesNotExist if not found."""
        return await cls.objects.aget(phone=phone)

    @classmethod
    async def aget_by_phone_or_none(cls, phone: str) -> "Candidate | None":
        """Fetch by phone — returns None instead of raising."""
        try:
            return await cls.objects.aget(phone=phone)
        except cls.DoesNotExist:
            return None

    # ── Async state helpers ────────────────────────────────────────────

    async def amark_response(self, status: str, via: str) -> None:
        """Atomically update status + responded_via + responded_at."""
        self.status        = status
        self.responded_via = via
        self.responded_at  = timezone.now()
        await self.asave(update_fields=["status", "responded_via", "responded_at"])

    async def amark_sent(self) -> None:
        """Mark candidate as notified after initial WhatsApp send."""
        self.status               = "sent"
        self.notification_sent_at = timezone.now()
        await self.asave(update_fields=["status", "notification_sent_at"])

    async def ais_already_decided(self) -> bool:
        """True if candidate already responded — skip re-processing."""
        return self.status in ("interested", "not_interested")

    async def arefresh(self) -> "Candidate":
        """Re-fetch latest state from DB — useful after Celery task updates."""
        await self.arefresh_from_db()
        return self


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

    # ── Async write ────────────────────────────────────────────────────

    @classmethod
    async def alog(
        cls,
        candidate: Candidate,
        channel: str,
        direction: str,
        sender: str,
        message: str,
        ai_detected_status: str | None = None,
    ) -> "ConversationLog | None":
        """
        Create a log entry. Never raises — webhook must never crash
        because of a logging failure.
        """
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

    # ── Async read ─────────────────────────────────────────────────────

    @classmethod
    async def aget_recent(
        cls,
        candidate: Candidate,
        channel: str = "whatsapp",
        limit: int = 5,
    ) -> list[dict]:
        """
        Returns last N messages as plain dicts for AI conversation history.

        Uses sync_to_async with a single DB hit — queryset slicing
        cannot be awaited directly in Django ORM.
        """
        @sync_to_async
        def _fetch() -> list[dict]:
            qs = (
                cls.objects
                .filter(candidate=candidate, channel=channel)
                .order_by("-created_at")
                .values("sender", "message")[:limit]
            )
            return list(reversed(list(qs)))

        return await _fetch()

    @classmethod
    async def aget_last_inbound(
        cls,
        candidate: Candidate,
        channel: str = "whatsapp",
    ) -> "ConversationLog | None":
        """Returns the most recent inbound message from the candidate."""
        try:
            return await cls.objects.filter(
                candidate=candidate,
                channel=channel,
                direction="inbound",
            ).alatest("created_at")
        except cls.DoesNotExist:
            return None

    @classmethod
    async def acount_today(
        cls,
        candidate: Candidate,
        channel: str = "whatsapp",
    ) -> int:
        """
        Count messages today — used for rate limiting checks.
        """
        from django.utils.timezone import now
        today = now().date()

        @sync_to_async
        def _count() -> int:
            return cls.objects.filter(
                candidate=candidate,
                channel=channel,
                created_at__date=today,
            ).count()

        return await _count()