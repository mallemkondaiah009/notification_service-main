from django.db import models


class Candidate(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("sent", "Notification Sent"),
        ("interested", "Interested"),
        ("not_interested", "Not Interested"),
    )

    RESPONDED_VIA_CHOICES = (
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
        ("call", "Call"),
    )

    # basic info
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    role_name = models.CharField(max_length=200)
    job_description = models.TextField()

    # notification status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    notification_sent_at = models.DateTimeField(null=True, blank=True)

    # response tracking
    responded_via = models.CharField(
        max_length=20,
        choices=RESPONDED_VIA_CHOICES,
        null=True,
        blank=True,
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class ConversationLog(models.Model):
    CHANNEL_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("call", "Call"),
    ]

    DIRECTION_CHOICES = [
        ("outbound", "Outbound"),
        ("inbound", "Inbound"),
    ]

    SENDER_CHOICES = [
        ("system", "System"),
        ("ai", "AI"),
        ("candidate", "Candidate"),
    ]

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="conversation_logs",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES)
    message = models.TextField()
    ai_detected_status = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="interested / not_interested / unclear",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.channel}] {self.candidate} | {self.sender} | {self.created_at}"