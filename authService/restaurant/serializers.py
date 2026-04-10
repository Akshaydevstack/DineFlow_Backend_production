from rest_framework import serializers
from .models import Restaurant, Table, RestaurantZone
from rest_framework import serializers
from .models import Restaurant
from accounts.models import CustomUserModel
from django.utils import timezone
import logging
from kafka.restaurant_producer import publish_restaurant_event
logger = logging.getLogger(__name__)
# =============================
# 🔹 Super-admin serializer
# =============================

class SuperAdminRestaurantManagementSerializer(serializers.ModelSerializer):
    public_id = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(required=False)
    is_open = serializers.BooleanField(required=False)

    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Restaurant
        fields = [
            "public_id",
            "name",
            "slug",
            "address",
            "city",
            "state",
            "pincode",
            "latitude",
            "longitude",
            "phone",
            "email",
            "is_open",
            "opening_time",
            "closing_time",
            "gst_number",
            "fssai_license",
            "commission_rate",
            "is_active",
            "created_at",
            "updated_at",
        ]

    # -----------------------
    # Email Validation
    # -----------------------
    def validate_email(self, value):
        if value:
            qs = Restaurant.objects.filter(email=value)

            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError(
                    "Restaurant with this email already exists"
                )

        return value


    # -----------------------
    # Phone Validation
    # -----------------------
    def validate_phone(self, value):

        if len(value) < 10 or len(value) > 15:
            raise serializers.ValidationError(
                "Phone number must be between 10 and 15 digits"
            )

        qs = Restaurant.objects.filter(phone=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "Restaurant with this phone number already exists"
            )

        return value


    # -----------------------
    # Pincode Validation
    # -----------------------
    def validate_pincode(self, value):

        if not value.isdigit():
            raise serializers.ValidationError(
                "Pincode must contain only digits"
            )

        if len(value) not in [5, 6]:
            raise serializers.ValidationError(
                "Pincode must be 5 or 6 digits"
            )

        return value


    # -----------------------
    # Commission Validation
    # -----------------------
    def validate_commission_rate(self, value):

        if value < 0:
            raise serializers.ValidationError(
                "Commission rate cannot be negative"
            )

        if value > 100:
            raise serializers.ValidationError(
                "Commission rate cannot exceed 100%"
            )

        return value


    # -----------------------
    # Latitude Validation
    # -----------------------
    def validate_latitude(self, value):

        if value is not None:
            if value < -90 or value > 90:
                raise serializers.ValidationError(
                    "Latitude must be between -90 and 90"
                )

        return value


    # -----------------------
    # Longitude Validation
    # -----------------------
    def validate_longitude(self, value):

        if value is not None:
            if value < -180 or value > 180:
                raise serializers.ValidationError(
                    "Longitude must be between -180 and 180"
                )

        return value


    # -----------------------
    # Opening / Closing Time
    # -----------------------
    def validate(self, data):

        opening_time = data.get("opening_time")
        closing_time = data.get("closing_time")

        if opening_time and closing_time and opening_time >= closing_time:
            raise serializers.ValidationError(
                {"timing": "Opening time must be before closing time"}
            )

        return data

    # -----------------------
    # Event Triggers (Kafka)
    # -----------------------
    def create(self, validated_data):
        # 1. Create the instance via standard DRF flow
        instance = super().create(validated_data)
        
        # 2. Fire the Kafka event
        try:
            publish_restaurant_event(instance, event_type="restaurant.created")
        except Exception as e:
            logger.error(f"❌ Failed to publish restaurant.created event for {instance.public_id}: {e}")
            
        return instance

    def update(self, instance, validated_data):
        # 1. Update the instance via standard DRF flow
        instance = super().update(instance, validated_data)
        
        # 2. Fire the Kafka event
        try:
            publish_restaurant_event(instance, event_type="restaurant.updated")
        except Exception as e:
            logger.error(f"❌ Failed to publish restaurant.updated event for {instance.public_id}: {e}")
            
        return instance



# RESTORNET ADMIN CREATED AUTOMATICALY ONCE THE RESTORENT IS CRAETED


class RestaurantAdminCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUserModel
        fields = [
            "email",
            "mobile_number",
            "first_name",
            "password",
        ]

    def validate_email(self, value):
        if CustomUserModel.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Admin with this email already exists"
            )
        return value

    def validate_mobile_number(self, value):
        if CustomUserModel.objects.filter(mobile_number=value).exists():
            raise serializers.ValidationError(
                "Admin with this mobile number already exists"
            )
        return value

    def create(self, validated_data):
        """
        Context MUST contain `restaurant_id`
        """
        restaurant_id = self.context.get("restaurant_id")
        if not restaurant_id:
            raise serializers.ValidationError(
                "restaurant_id missing in serializer context"
            )

        try:
            restaurant = Restaurant.objects.get(public_id=restaurant_id)
        except Restaurant.DoesNotExist:
            raise serializers.ValidationError("Invalid restaurant")

        user = CustomUserModel.objects.create_user(
            email=validated_data["email"],
            mobile_number=validated_data["mobile_number"],
            first_name=validated_data["first_name"],
            password=validated_data["password"],
            restaurant=restaurant,
            is_staff=True,
            role="restaurant-admin",
        )

        return user



# =============================
# 🔹 Restaurant-admin serializer
# =============================

class RestaurantAdminRestaurantSerializer(serializers.ModelSerializer):
    
    # 1️⃣ Add a custom field for the admin details
    admin_details = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            "public_id",
            "name",
            "slug",
            "address",
            "city",
            "state",
            "pincode",
            "latitude",
            "longitude",
            "phone",
            "email",
            "is_open",
            "opening_time",
            "closing_time",
            "gst_number",
            "fssai_license",
            "updated_at",
            "created_at",
            "admin_details",  # 2️⃣ Add it to the fields list
        ]

        read_only_fields = [
            "public_id",
            "updated_at",
            "created_at",
            "admin_details",  # 3️⃣ Make sure it cannot be updated via this endpoint
        ]

    # 4️⃣ Define how to fetch the admin details
    def get_admin_details(self, obj):
        """
        Fetches the primary admin associated with this restaurant.
        Assumes CustomUserModel has a ForeignKey/OneToOne to Restaurant.
        """
        admin = CustomUserModel.objects.filter(
            restaurant=obj, 
            role="restaurant-admin"
        ).first()

        if admin:
            return {
                "public_id": admin.public_id,
                "first_name": admin.first_name,
                "last_name": admin.last_name,
                "email": admin.email,
                "mobile_number": admin.mobile_number,
                "created_at": admin.created_at,
                "updated_at": admin.updated_at
            }
        
        return None

    def validate(self, data):
        opening_time = data.get("opening_time")
        closing_time = data.get("closing_time")

        if opening_time and closing_time and opening_time >= closing_time:
            raise serializers.ValidationError(
                {"timing": "Opening time must be before closing time"}
            )

        return data

    # -----------------------
    # Event Triggers (Kafka)
    # -----------------------
    def update(self, instance, validated_data):
        """
        Override update to publish Kafka event when restaurant details 
        (like location, name, hours) are changed by the admin.
        """
        # 1. Update the instance via standard DRF flow
        instance = super().update(instance, validated_data)
        
        # 2. Fire the Kafka event so other services (Order, Cart, Menu) know about the change
        try:
            publish_restaurant_event(instance, event_type="restaurant.updated")
        except Exception as e:
            logger.error(f"❌ Failed to publish restaurant.updated event for {instance.public_id}: {e}")
            
        return instance




class RestaurantAdminZoneSerializer(serializers.ModelSerializer):
    restaurant_id = serializers.CharField(
        source="restaurant.public_id",
        read_only=True
    )

    class Meta:
        model = RestaurantZone
        fields = [
            "public_id",
            "restaurant_id",
            "is_active",
            "name",
        ]
        read_only_fields = [
            "public_id",
            "restaurant_id",
        ]

    # Removed validate() and create() because the ViewSet 
    # now injects the restaurant directly into save().

    def update(self, instance, validated_data):
        instance.name = validated_data.get("name", instance.name)
        instance.is_active = validated_data.get("is_active", instance.is_active)

        # bump version
        current_version = int(instance.zone_version.lstrip("v"))
        instance.zone_version = f"v{current_version + 1}"

        instance.save()
        return instance


# ---------------------------------------------------------
# Table Serializer
# ---------------------------------------------------------
class RestaurantAdminTableSerializer(serializers.ModelSerializer):
    restaurant_id = serializers.CharField(
        source="restaurant.public_id",
        read_only=True
    )

    qr_url = serializers.CharField(read_only=True)

    zone = serializers.SlugRelatedField(
        slug_field="public_id",
        queryset=RestaurantZone.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Table
        fields = [
            "public_id",
            "restaurant_id",
            "table_number",
            "capacity",
            "table_type",
            "zone",
            "is_active",
            "is_occupied",
            "is_reserved_manual",
            "occupied_by_user_id",
            "qr_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "qr_url",
            "table_version",
            "created_at",
            "updated_at",
            "restaurant_id",
            "is_occupied",
            "occupied_by_user_id",
        ]

    def validate_zone(self, zone):
        if not zone:
            return zone
            
        request = self.context["request"]
        restaurant_id = request.headers.get("X-Restaurant-Id")

        if zone.restaurant.public_id != restaurant_id:
            raise serializers.ValidationError("Zone does not belong to this restaurant")

        return zone

    def validate(self, attrs):
        # We only use validate here to ensure the table number is unique 
        # within the specific restaurant.
        request = self.context["request"]
        restaurant_id = request.headers.get("X-Restaurant-Id")

        if not restaurant_id:
            raise serializers.ValidationError("X-Restaurant-Id header missing")

        # Get table number (handles both creation and partial updates)
        table_number = attrs.get(
            "table_number",
            self.instance.table_number if self.instance else None
        )

        qs = Table.objects.filter(
            restaurant__public_id=restaurant_id,
            table_number=table_number
        )

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                {"table_number": "Table number already exists in this restaurant"}
            )

        # NOTE: We intentionally DO NOT do attrs["restaurant"] = restaurant anymore.
        return attrs

# =============================
# 🔹 Restaurant-Users serializer for getting the deatils of the restorent
# =============================

class RestaurantUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = [
            "name",
            "address",
            "city",
            "state",
            "pincode",
            "phone",
            "email",
            "is_open",
            "opening_time",
            "closing_time",
        ]


# =============================
# 🔹 Restaurant-WAITER
# =============================

class WaiterZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantZone
        fields = [
            "public_id",
            "name",
            "zone_version",
        ]



# for waiter to book the table of a customer


class WaiterTableSerializer(serializers.ModelSerializer):
    zone = RestaurantAdminZoneSerializer(read_only=True)
    can_book = serializers.SerializerMethodField()
    can_order = serializers.SerializerMethodField()
    active_reservation = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = [
            "public_id",
            "table_number",
            "capacity",
            "zone",
            "table_type",
            "is_occupied",
            "occupied_by_user_id",
            "is_reserved_manual",
            "active_reservation",
            "can_book",
            "can_order",
            "qr_url",
        ]

    def get_can_book(self, obj):
        now = timezone.now()

        has_active_reservation = obj.reservations.filter(
            status__in=["pending", "confirmed"],
            end_time__gte=now
        ).exists()

        return (
            obj.is_active and
            not obj.is_occupied and
            not obj.is_reserved_manual and
            not has_active_reservation
        )

    def get_can_order(self, obj):
        return obj.is_active and not obj.is_reserved_manual


    def get_active_reservation(self, obj):
        now = timezone.now()

        reservation = obj.reservations.filter(
            status__in=["pending", "confirmed", "seated"],
            end_time__gte=now
        ).order_by("reservation_time").first()

        if not reservation:
            return None

        return {
            "public_id": reservation.public_id,
            "customer_name": reservation.user.username,
            "guest_count": reservation.guest_count,
            "status": reservation.status,
            "reservation_time": reservation.reservation_time,
            "end_time": reservation.end_time,
            "time_window": f"{reservation.reservation_time.strftime('%I:%M %p')} - {reservation.end_time.strftime('%I:%M %p')}"
        }