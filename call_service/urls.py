from django.urls import path
from .views import call_twiml, call_response

urlpatterns = [
    path("twiml/", call_twiml),
    path("response/", call_response),
]