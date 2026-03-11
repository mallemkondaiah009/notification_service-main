from rest_framework import serializers


class NotificationSerializer(serializers.Serializer):
    candidate_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of candidate IDs, e.g. [1, 2, 3]"
    )