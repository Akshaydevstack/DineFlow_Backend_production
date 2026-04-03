from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "body",
            "topic",
            "reference_id",
            "is_read",
            "created_at",
        ]


class RestaurantAdminBroadcastNotificationSerializer(serializers.Serializer):

    title = serializers.CharField(max_length=150)
    body = serializers.CharField()

    role = serializers.CharField(
        required=False,
        allow_blank=True
    )


class BroadcastNotificationListSerializer(serializers.Serializer):

    reference_id = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()