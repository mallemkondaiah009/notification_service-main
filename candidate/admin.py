from django.contrib import admin
from .models import Candidate, ConversationLog


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
    "full_name",
    "email",
    "phone",
    "role_name",
    "status",
    "responded_via",
    "responded_at",
    "created_at",
)
list_filter = (
    "status",
    "responded_via",
    "created_at",
)
readonly_fields = (
    "notification_sent_at",
    "responded_via",
    "responded_at",
    "created_at",
)


class ConversationLogInline(admin.TabularInline):
    model = ConversationLog
    extra = 0
    readonly_fields = [
        "channel",
        "direction",
        "sender",
        "message",
        "ai_detected_status",
        "created_at",
    ]
    ordering = ["created_at"]
    can_delete = False

@admin.register(ConversationLog)
class ConversationLogAdmin(admin.ModelAdmin):
    list_display = [
        "candidate",
        "channel",
        "direction",
        "sender",
        "ai_detected_status",
        "short_message",
        "created_at",
    ]
    list_filter = ["channel", "direction", "sender", "ai_detected_status"]
    search_fields = ["candidate__full_name", "message"]
    ordering = ["-created_at"]

    def short_message(self, obj):
        return obj.message[:80] + "..." if len(obj.message) > 80 else obj.message
    short_message.short_description = "Message"