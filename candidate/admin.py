from django.contrib import admin
from .models import JobDescription, Candidate, ConversationLog


@admin.register(JobDescription)
class JobDescriptionAdmin(admin.ModelAdmin):
    list_display  = ["id", "title", "created_at", "updated_at"]
    search_fields = ["title", "content"]
    ordering      = ["-created_at"]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display  = ["full_name", "phone", "role_name", "job", "status", "responded_via", "created_at"]
    list_filter   = ["status", "responded_via", "job"]
    search_fields = ["full_name", "phone", "role_name"]
    ordering      = ["-created_at"]


@admin.register(ConversationLog)
class ConversationLogAdmin(admin.ModelAdmin):
    list_display  = ["candidate", "channel", "direction", "sender", "ai_detected_status","message", "created_at"]
    list_filter   = ["channel", "direction", "sender", "ai_detected_status"]
    search_fields = ["candidate__full_name", "message"]
    ordering      = ["-created_at"]