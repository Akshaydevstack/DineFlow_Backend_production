from rest_framework import serializers
from .models import CustomUserModel
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
from auth_service.firebase import firebase_auth
from django.contrib.auth import authenticate
from restaurant.models import Restaurant
from restaurant.models import Restaurant, Table, Reservation
from django.utils import timezone
from kafka.user_producer import publish_user_created_event
import threading
import uuid
from loguru import logger

class ValidateScanSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)
    restaurant_id = serializers.CharField(max_length=50)
    current_table_id = serializers.CharField(max_length=50)
    qr_code_token = serializers.CharField(max_length=50)

    def validate(self, attrs):
        mobile = attrs.get("mobile_number")
        rest_id = attrs.get("restaurant_id")
        table_id = attrs.get("current_table_id")
        qr_token_input = attrs.get("qr_code_token")

        try:
            restaurant = Restaurant.objects.get(
                public_id=rest_id, is_active=True)
        except Restaurant.DoesNotExist:
            raise serializers.ValidationError(
                {"restaurant_id": "Invalid Restaurant"})

        try:
            table = Table.objects.get(
                public_id=table_id,
                restaurant=restaurant,
                is_active=True
            )
        except Table.DoesNotExist:
            raise serializers.ValidationError(
                {"current_table_id": "Invalid Table or does not belong to this restaurant."}
            )

        if table.is_reserved_manual:
            raise serializers.ValidationError(
                {"current_table_id": "This table is manually reserved. Please contact staff."}
            )

                # If table is occupied
        if table.is_occupied:

            internal_username = f"{rest_id}_{mobile}"

            existing_user = CustomUserModel.objects.filter(
                username=internal_username,
                is_staff=False
            ).first()

            # If table is occupied by someone else → block
            if not existing_user or table.occupied_by_user_id != existing_user.public_id:
                raise serializers.ValidationError(
                    {"current_table_id": "This table is currently occupied."}
                )

            # If same user → allow re-login

        now = timezone.now()

        active_reservation = Reservation.objects.filter(
            table=table,
            restaurant=restaurant,
            status="confirmed",
            reservation_time__lte=now,
            end_time__gte=now
        ).first()

        if active_reservation:
            res_mobile = active_reservation.user.mobile_number
            input_mobile = mobile

            if res_mobile != input_mobile:
                raise serializers.ValidationError(
                    {"current_table_id": f"Reserved for {active_reservation.user.first_name} at this time."}
                )

        if str(table.qr_code_token) != qr_token_input:
            raise serializers.ValidationError(
                {"qr_code_token": "Invalid QR Code. Please rescan."}
            )
        
        if not restaurant.is_open:
            raise serializers.ValidationError(
                {"Restaurant": "Restaurant is currently closed "}
            )


        internal_username = f"{rest_id}_{mobile}"

        user = CustomUserModel.objects.filter(
            username=internal_username, is_staff=False
        ).first()

        if user:
            if not user.is_active:
                raise serializers.ValidationError({
                    "mobile_number": (
                        "Your account has been blocked by admin. "
                        "Please contact support for more details."
                    )
                })

            raise serializers.ValidationError({
                "mobile_number": "User already exists."
            })

        return attrs
    



class RegisterSerializer(serializers.ModelSerializer):
    firebase_token = serializers.CharField(write_only=True)
    restaurant_id = serializers.CharField(write_only=True)
    current_table_id = serializers.CharField(write_only=True)
    qr_code_token = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUserModel
        fields = (
            "email",
            "mobile_number",
            "first_name",
            "firebase_token",
            "restaurant_id",
            "current_table_id",
            "qr_code_token"
        )

    def validate(self, data):
        # ... (Your existing validation code remains exactly the same) ...
        email = data.get("email")
        mobile_number = data.get("mobile_number")
        firebase_token = data.get("firebase_token")
        restaurant_id = data.get("restaurant_id")
        current_table_id = data.get("current_table_id")
        qr_code_token = data.get("qr_code_token")

        errors = {}

        try:
            restaurant = Restaurant.objects.get(
                public_id=restaurant_id,
                is_active=True
            )
        except Restaurant.DoesNotExist:
            raise serializers.ValidationError({"restaurant_id": "Invalid restaurant"})

        if current_table_id:
            try:
                table = Table.objects.get(
                    public_id=current_table_id,
                    restaurant=restaurant,
                    qr_code_token=qr_code_token,
                    is_active=True
                )
            except Table.DoesNotExist:
                errors["current_table_id"] = "Invalid Table ID or Table does not belong to this restaurant."

        internal_username = f"{restaurant_id}_{mobile_number}"

        # OPTIMIZATION: .exists() is faster than .first() here
        if CustomUserModel.objects.filter(username=internal_username).exists():
            errors["mobile_number"] = "User already registered at this restaurant. Please login."

        if errors:
            raise serializers.ValidationError(errors)

        try:
            # This blocks, but it HAS to block for security.
            decoded_token = firebase_auth.verify_id_token(
                firebase_token, check_revoked=True)
        except Exception:
            raise serializers.ValidationError({"firebase_token": "Invalid Firebase token"})

        verified_phone = decoded_token.get("phone_number")
        if verified_phone != mobile_number:
            raise serializers.ValidationError({"mobile_number": f"Mobile mismatch. Token is for {verified_phone}"})

        data["restaurant_obj"] = restaurant
        return data


    def create(self, validated_data):
        validated_data.pop("firebase_token")
        validated_data.pop("restaurant_id")
        if "current_table_id" in validated_data:
            validated_data.pop("current_table_id")

        restaurant = validated_data.pop("restaurant_obj")
        mobile = validated_data.get("mobile_number")
        internal_username = f"{restaurant.public_id}_{mobile}"
        random_password = str(uuid.uuid4())

        # ⚡ OPTIMIZED TRANSACTION BLOCK
        with transaction.atomic():
            user = CustomUserModel.objects.create_user(
                username=internal_username,
                email=validated_data.get("email"),
                mobile_number=mobile,
                password=random_password,
                restaurant=restaurant,
                first_name=validated_data.get("first_name", ""),
                role="customer",
            )
            user.set_unusable_password()
            user.save()

            # ⚡ THE FIX: Run Kafka publish ONLY after Postgres commits successfully, 
            # and push it to a background thread so the API responds instantly.
            transaction.on_commit(
                lambda: threading.Thread(
                    target=self._publish_in_background,
                    args=(user,)
                ).start()
            )

        return user

    def _publish_in_background(self, user):
        """Helper method to handle the background Kafka publish safely."""
        try:
            publish_user_created_event(user=user)
            logger.info(f"Background Kafka publish successful for user: {user.username}")
        except Exception as e:
            # If Kafka fails, the user is still registered in Postgres, 
            # but we don't crash their login experience!
            logger.error(f"Background Kafka publish failed for user {user.username}: {e}")


class LoginWithFirebaseSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(required=True)
    firebase_token = serializers.CharField(write_only=True)
    restaurant_id = serializers.CharField(write_only=True)
    current_table_id = serializers.CharField(write_only=True)
    qr_code_token = serializers.CharField(write_only=True)

    def validate(self, data):
        mobile_number = data.get("mobile_number")
        firebase_token = data.get("firebase_token")
        restaurant_id = data.get("restaurant_id")
        current_table_id = data.get("current_table_id")
        qr_code_token = data.get("qr_code_token")

        try:
            restaurant = Restaurant.objects.get(
                public_id=restaurant_id,
                is_active=True
            )

        except Restaurant.DoesNotExist:
            raise serializers.ValidationError(
                {"restaurant_id": "Invalid restaurant"})

        try:
            table = Table.objects.get(
                public_id=current_table_id,
                restaurant=restaurant,
                qr_code_token=qr_code_token,
                is_active=True
            )
        except Table.DoesNotExist:
            raise serializers.ValidationError(
                {"Invalid Table ID or Table does not belong to this restaurant."})

        try:
            decoded_token = firebase_auth.verify_id_token(
                firebase_token, check_revoked=True
            )
        except firebase_auth.InvalidIdTokenError:
            raise serializers.ValidationError(
                {"firebase_token": "Invalid Firebase token"}
            )

        except firebase_auth.ExpiredIdTokenError:
            raise serializers.ValidationError(
                {"firebase_token": "Expired Firebase token"}
            )

        verified_phone = decoded_token.get("phone_number")

        if verified_phone != mobile_number:
            raise serializers.ValidationError(
                {"mobile_number": "Mobile number mismatch with verified token"}
            )

        internal_username = f"{restaurant.public_id}_{mobile_number}"

        try:
            user = CustomUserModel.objects.get(
                username=internal_username,
                is_staff=False
            )

            if not user.is_active:
                raise serializers.ValidationError(
                    {"error": "Your account has been blocked by admin. please contact support for more details"}
                )
        except CustomUserModel.DoesNotExist:

            raise serializers.ValidationError(
                {"error": "User does not exist at this restaurant. Please register first."}
            )

        data["user"] = user
        return data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["name"] = user.first_name
        token["user_id"] = user.id
        token["public_id"] = user.public_id
        token["email"] = user.email
        token["role"] = user.role
        token["mobile_number"] = user.mobile_number
        token["is_active"] = user.is_active
        token["is_superadmin"] = user.is_superadmin
        token["is_staff"] = user.is_staff
        token["restaurant_id"] = (
            str(user.restaurant.public_id) if user.restaurant else None
        )

        return token





# ===============================
# 🔹 Restaurant-admin-serializers
# ===============================


# =========================================================
# 🔹 READ SERIALIZER
# =========================================================

class EmployeeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUserModel
        fields = (
            "public_id",
            "username",
            "first_name",
            "email",
            "mobile_number",
            "role",
            "is_active",
            "created_at",
            "updated_at",
            "is_staff",
        )


# =========================================================
# 🔹 CREATE SERIALIZER
# =========================================================

class EmployeeCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        required=True
    )

    class Meta:
        model = CustomUserModel
        fields = (
            "public_id",
            "first_name",
            "username",
            "email",
            "mobile_number",
            "role",
            "password",
        )

        read_only_fields = (
            "public_id",
            "username",   
        )

    # ----------------------------
    # Role Validation
    # ----------------------------
    def validate_role(self, value):
        allowed_roles = ("restaurant-admin", "waiter", "kitchen-staff")
        if value not in allowed_roles:
            raise serializers.ValidationError("Invalid employee role")
        return value

    # ----------------------------
    # Mobile Unique Per Restaurant
    # ----------------------------
    def validate_mobile_number(self, value):
        restaurant = self.context["view"].get_restaurant()

        if CustomUserModel.objects.filter(
            restaurant=restaurant,
            mobile_number=value,
            is_staff=True
        ).exists():
            raise serializers.ValidationError(
                "Mobile number already exists for this restaurant"
            )

        return value

    # ----------------------------
    # Create
    # ----------------------------
    def create(self, validated_data):
        password = validated_data.pop("password")
        restaurant = validated_data.pop("restaurant")

        user = CustomUserModel.objects.create_user(
            password=password,
            restaurant=restaurant,
            is_staff=True,
            **validated_data
        )

        return user


# =========================================================
# 🔹 UPDATE SERIALIZER
# =========================================================

class EmployeeUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        required=False
    )

    class Meta:
        model = CustomUserModel
        fields = (
            "public_id",            
            "first_name",
            "email",
            "mobile_number",
            "username",
            "role",
            "is_active",
            "password",
        )
        read_only_fields = (
            "public_id",
            "username",   
        )
        extra_kwargs = {
            "first_name": {"required": False},
            "email": {"required": False},
            "mobile_number": {"required": False},
            "role": {"required": False},
            "is_active": {"required": False},
        }

    # ----------------------------
    # Role Validation
    # ----------------------------
    def validate_role(self, value):
        allowed_roles = ("restaurant-admin", "waiter", "kitchen-staff")
        if value not in allowed_roles:
            raise serializers.ValidationError("Invalid employee role")
        return value

    # ----------------------------
    # Mobile Unique Per Restaurant
    # ----------------------------
    def validate_mobile_number(self, value):
        user = self.instance
        restaurant = user.restaurant

        if CustomUserModel.objects.filter(
            restaurant=restaurant,
            mobile_number=value,
            is_staff=True
        ).exclude(id=user.id).exists():
            raise serializers.ValidationError(
                "Mobile number already exists for this restaurant"
            )

        return value

    # ----------------------------
    # Update
    # ----------------------------
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance




# only for employee loogin
class EmployeeLoginSerializer(serializers.Serializer):
    user_name = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username = data.get("user_name")
        password = data.get("password")

        user = authenticate(username=username, password=password)

        if not user:
            raise serializers.ValidationError(
                {"error": "Invalid username or password"}
            )

        if (
            not user.is_staff or
            user.role not in ("waiter", "kitchen-staff", "restaurant-admin")
        ):
            raise serializers.ValidationError(
                {"error": "You are not allowed to login as employee"}
            )

        data["user"] = user
        return data



class RestaurantAdminCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUserModel
        fields = [
            "public_id",
            "first_name",
            "mobile_number",
            "email",
            "is_active",
            "created_at",
            "auth_version",
        ]
        read_only_fields = fields


#==========================
# Super admin serializer
#==========================

class SuperAdminLoginSerializer(serializers.Serializer):
    user_name = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username = data.get("user_name")
        password = data.get("password")

        user = authenticate(username=username, password=password)

        if not user:
            raise serializers.ValidationError(
                {"error": "Invalid username or password"}
            )

        if not user.is_superadmin or user.role != "super-admin":
            raise serializers.ValidationError(
                {"error": "You are not allowed to login as Super Admin"}
            )

        data["user"] = user
        return data


class StaffSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomUserModel
        fields = [
            "public_id",
            "username",
            "first_name",
            "mobile_number",
            "email",
            "role",
            "is_active",
            "created_at",
            "updated_at"
        ]

class SuperAdminCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUserModel
        fields = [
            "public_id",
            "first_name",
            "mobile_number",
            "email",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields