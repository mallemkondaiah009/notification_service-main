from django.urls import path
from .views import WhatsAppWebhook

urlpatterns = [
    path("webhook/", WhatsAppWebhook.as_view()),
]