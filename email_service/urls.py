from django.urls import path
from .views import email_webhook

urlpatterns = [
    path("webhook/", email_webhook),
]