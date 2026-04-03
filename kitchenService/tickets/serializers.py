from rest_framework import serializers
from .models import KitchenTicket, KitchenItem


class KitchenItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = KitchenItem
        fields = [
            "id",
            "dish_id",
            "dish_name",
            "quantity",
            "status",
            "started_at",
            "finished_at",
            "prep_time_seconds",
            "estimated_prep_time_seconds",
        ]
        read_only_fields = [
            "started_at",
            "finished_at",
            "prep_time_seconds",
        ]


class KitchenTicketListSerializer(serializers.ModelSerializer):
    items = KitchenItemSerializer(many=True, read_only=True)

    class Meta:
        model = KitchenTicket
        fields = [
            "public_id",
            "order_id",
            "restaurant_id",
            "user_id",
            "status",
            "created_at",
            "accepted_at",
            "preparing_at",
            "ready_at",
            "items",
        ]


class KitchenTicketDetailSerializer(serializers.ModelSerializer):
    items = KitchenItemSerializer(many=True, read_only=True)

    class Meta:
        model = KitchenTicket
        fields = "__all__"