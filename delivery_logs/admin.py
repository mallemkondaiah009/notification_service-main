from django.contrib import admin
from .models import DeliveryLog


@admin.register(DeliveryLog)
class DeliveryLogAdmin(admin.ModelAdmin):
    list_display = (
        "candidate",
        "channel",
        "recipient",
        "status",
        "retry_count",
        "created_at",
    )
    list_filter = (
        "channel",
        "status",
        "created_at",
    )
    search_fields = (
        "candidate__full_name",
        "candidate__email",
        "recipient",
        "error_message",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "candidate",
        "channel",
        "recipient",
        "message",
        "status",
        "retry_count",
        "error_message",
        "created_at",
    )