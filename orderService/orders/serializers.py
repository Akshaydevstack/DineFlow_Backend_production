from rest_framework import serializers
from .models import Order, OrderItem
from decimal import Decimal
from .models import Order, OrderItem, TableSession
from common.tenant import get_tenant_context
from .models import MenuItemSnapshot, TableSnapshot, Restaurant
from utils.calculate_distance import calculate_distance 



class OrderCreateSerializer(serializers.Serializer):
    table_public_id = serializers.CharField(max_length=20)
    special_request = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=500   # prevent abuse
    )
    
    # ⚡ FIX: Added fields to accept coordinates from frontend payload
    user_latitude = serializers.FloatField(required=True)
    user_longitude = serializers.FloatField(required=True)
    
    items = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False
    )

    # ---------------------------------
    # Basic Item Validation
    # ---------------------------------
    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Items list cannot be empty")

        for index, item in enumerate(items):
            if "dish_id" not in item:
                raise serializers.ValidationError(f"Item {index}: dish_id is required")

            if "quantity" not in item:
                raise serializers.ValidationError(f"Item {index}: quantity is required")

            try:
                quantity = int(item["quantity"])
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"Item {index}: quantity must be an integer")

            if quantity <= 0:
                raise serializers.ValidationError(f"Item {index}: quantity must be greater than 0")

        return items

    # ---------------------------------
    # Full Business & Location Validation
    # ---------------------------------
    def validate(self, attrs):
        request = self.context["request"]
        restaurant_id, user_id = get_tenant_context(request)

        table_public_id = attrs["table_public_id"]
        items = attrs["items"]
        user_lat = attrs["user_latitude"]
        user_lon = attrs["user_longitude"]

        # ---------------------------------
        # 📍 Geofencing Validation (20 Meters)
        # ---------------------------------
        try:
            restaurant = Restaurant.objects.get(public_id=restaurant_id)
            
            # Only enforce if the restaurant admin has actually set their coordinates
            if restaurant.latitude and restaurant.longitude:
                distance = calculate_distance(
                    user_lat, user_lon, 
                    restaurant.latitude, restaurant.longitude
                )
                
                # ⚡ Check if distance exceeds 20 meters
                if distance > 20:
                    raise serializers.ValidationError(
                        {"location": f"You are too far from the restaurant to place an order. Please move closer. (Distance: {int(distance)}m)"}
                    )
        except Restaurant.DoesNotExist:
            raise serializers.ValidationError(
                {"restaurant": "Restaurant details not found for location validation."}
            )

        # ---------------------------------
        # Validate Table Snapshot
        # ---------------------------------
        table_snapshot = TableSnapshot.objects.filter(
            restaurant_id=restaurant_id,
            table_public_id=table_public_id,
            is_active=True,
        ).first()

        if not table_snapshot:
            raise serializers.ValidationError(
                {"table_public_id": "Invalid or inactive table"}
            )

        # ---------------------------------
        # Validate Session (Table Occupancy)
        # ---------------------------------
        active_session = TableSession.objects.filter(
            restaurant_id=restaurant_id,
            table_public_id=table_public_id,
            status=TableSession.STATUS_ACTIVE,
        ).first()

        if active_session:
            other_user_active_order_exists = active_session.orders.filter(
                status__in=[
                    Order.STATUS_CREATED,
                    Order.STATUS_ACCEPTED,
                    Order.STATUS_PREPARING,
                    Order.STATUS_READY,
                    Order.STATUS_PAID,
                ],
            ).exclude(user_id=user_id).exists()

            if other_user_active_order_exists:
                raise serializers.ValidationError(
                    {"table_public_id": "This table is currently occupied"}
                )

        # ---------------------------------
        # Validate Menu Snapshot
        # ---------------------------------
        dish_ids = [item["dish_id"] for item in items]

        snapshots = MenuItemSnapshot.objects.filter(
            restaurant_id=restaurant_id,
            dish_id__in=dish_ids,
            is_available=True,
        )

        snapshot_map = {s.dish_id: s for s in snapshots}

        missing = set(dish_ids) - set(snapshot_map.keys())
        if missing:
            raise serializers.ValidationError(
                {"items": f"Some items unavailable: {list(missing)}"}
            )

        # Attach validated objects
        attrs["restaurant_id"] = restaurant_id
        attrs["user_id"] = user_id
        attrs["table_snapshot"] = table_snapshot
        attrs["snapshot_map"] = snapshot_map
        attrs["active_session"] = active_session

        return attrs




class OrderItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "dish_id",
            "dish_name",
            "unit_price",
            "quantity",
            "total_price",
        ]


class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemReadSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            "public_id",
            "status",
            "payment_status",
            "paid_at",
            "subtotal",
            "tax",
            "discount",
            "total",
            "currency",
            "items",
            "created_at",
        ]




class TableSessionSerializer(serializers.ModelSerializer):

    class Meta:
        model = TableSession
        fields = [
            "public_id",
            "restaurant_id",
            "table_public_id",
            "table_number",
            "zone_public_id",
            "zone_name",
            "status",
            "started_at",
            "closed_at",
            "last_activity_at"
        ]
        read_only_fields = [
            "public_id",
            "started_at",
            "last_activity_at"
        ]