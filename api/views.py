import logging

from adrf.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from .serializers import NotificationSerializer
from workers.tasks import send_bulk_whatsapp_notifications

logger = logging.getLogger("api.views")


class SendNotificationAPIView(APIView):

    async def post(self, request: Request) -> Response:

        # ── Validate — raise_exception auto returns 400 on failure ─────
        serializer = NotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        candidate_ids = serializer.validated_data["candidate_ids"]
        campaign_id   = serializer.validated_data.get("campaign_id") or None

        # ── Queue task — Celery handles the rest ───────────────────────
        send_bulk_whatsapp_notifications.delay(candidate_ids, campaign_id)

        logger.info(
            "[API] Notifications queued — count=%d campaign=%s",
            len(candidate_ids), campaign_id,
        )

        return Response(
            {
                "message":       f"Notifications queued for {len(candidate_ids)} candidates",
                "candidate_ids": candidate_ids,
            },
            status=status.HTTP_200_OK,
        )