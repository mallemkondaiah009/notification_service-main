from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import NotificationSerializer
from workers.tasks import send_bulk_notifications


class SendNotificationAPIView(APIView):

    def post(self, request):
        serializer = NotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        candidate_ids = serializer.validated_data["candidate_ids"]
        send_bulk_notifications.delay(candidate_ids)

        return Response(
            {
                "message": f"Notifications queued for {len(candidate_ids)} candidates",
                "candidate_ids": candidate_ids,
            },
            status=status.HTTP_200_OK,
        )