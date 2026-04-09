from rest_framework.views import APIView
from .serializers import RegisterSerializer, LoginWithFirebaseSerializer
from rest_framework.response import Response
from rest_framework import status
from .serializers import CustomTokenObtainPairSerializer, ValidateScanSerializer, EmployeeLoginSerializer, EmployeeUpdateSerializer,StaffSerializer,UserProfileSerializer,UpdateMobileWithFirebaseSerializer
from .serializers import EmployeeReadSerializer, EmployeeCreateSerializer, SuperAdminLoginSerializer, RestaurantAdminCustomerSerializer,SuperAdminCustomerSerializer,UserAddressSerializer,AdminProfileUpdateSerializer
from rest_framework import permissions
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUserModel
from restaurant.models import Restaurant
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from .pagination import StandardResultsSetPagination
from django.db.models import Q,Count
from rest_framework.viewsets import ModelViewSet
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from .filters import EmployeeFilter
from kafka.user_producer import publish_user_updated_event
import threading
import random
from django.core.cache import cache
from django.conf import settings
from utils.send_email import send_email_background


@extend_schema(tags=["Helth"])
class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})



# check if the user is already exist
# helper for checking the user alredy exist

@extend_schema(tags=["Validate Scan"])
class ValidateScanView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ValidateScanSerializer(data=request.data)

        if not serializer.is_valid():
            errors = serializer.errors

            if "mobile_number" in errors and errors["mobile_number"][0] == "User already exists.":
                return Response(
                    {
                        "exists": True,
                        "message": "User already registered at this restaurant"
                    },
                    status=status.HTTP_200_OK
                )

            first_field_errors = next(iter(errors.values()))
            error_message_string = first_field_errors[0]
            return Response(
                {
                    "exists": False,
                    "errors": error_message_string,
                    "message": "Validation failed"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "exists": False,
                "message": "User not found, please register"
            },
            status=status.HTTP_200_OK
        )


# RegistrationView for customer̦
class UserRegistrationView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()
        table_id = request.data.get("current_table_id")
        refresh_token = CustomTokenObtainPairSerializer.get_token(user)
        access_token = refresh_token.access_token

        response = Response(
            {
                "message": "User registered successfully",
                "access_token": str(access_token),
                "current_table_id": table_id
            },
            status=status.HTTP_201_CREATED,
        )

        response.set_cookie(
            key="refresh_token",
            value=str(refresh_token),
            httponly=True,
            secure=True,
            samesite="None",
            path="/",
            max_age=60 * 60 * 24 * 7,
        )

        return response


# Login with OTP for coustemer

class UserLoginWithFirebaseView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginWithFirebaseSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.validated_data["user"]
        table_id = request.data.get("current_table_id")

        refresh_token = CustomTokenObtainPairSerializer.get_token(user)
        access_token = refresh_token.access_token

        response = Response(
            {
                "message": "User logged in successfully",
                "access_token": str(access_token),
                "current_table_id": table_id
            },
            status=status.HTTP_200_OK
        )

        response.set_cookie(
            key="refresh_token",
            value=str(refresh_token),
            httponly=True,
            secure=True,
            samesite="None",
            path="/",
            max_age=60 * 60 * 24 * 7,
        )

        return response


# for refershing the access token

class CookieTokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"error": "Refresh token missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            old_refresh = RefreshToken(refresh_token)
            user_id = old_refresh["user_id"]

            user = CustomUserModel.objects.get(id=user_id)

            if not user.is_active:
                return Response(
                    {"error": "User is blocked"},
                    status=status.HTTP_403_FORBIDDEN
                )
            new_refresh = CustomTokenObtainPairSerializer.get_token(user)
            new_access = new_refresh.access_token
            old_refresh.blacklist()

        except Exception:
            return Response(
                {"error": "Invalid refresh token"},
                status=status.HTTP_400_BAD_REQUEST
            )

        response = Response(
            {
                "message": "Token refreshed successfully",
                "access_token": str(new_access),
            },
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            key="refresh_token",
            value=str(new_refresh),
            httponly=True,
            secure=True,
            samesite="None",
            path="/",
            max_age=60 * 60 * 24 * 7,
        )

        return response


class UserProfileView(APIView):
    """
    API View to retrieve and update the profile of the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserProfileSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        user = request.user
        data = request.data.copy()
        
        # 🔴 PREVENT DIRECT MOBILE UPDATES
        # Force the frontend to use the secure Firebase endpoint for mobile numbers
        if "mobile_number" in data:
            data.pop("mobile_number")

        serializer = UserProfileSerializer(user, data=data, partial=True)

        if serializer.is_valid():
            updated_user = serializer.save()

            def send_kafka_event(user_obj):
                try:
                    publish_user_updated_event(user=user_obj)
                except Exception as e:
                    print(f"Kafka sync failed for user {user_obj.public_id}: {e}")

            threading.Thread(target=send_kafka_event, args=(updated_user,)).start()

            return Response({
                "message": "Profile updated successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateMobileWithFirebaseView(APIView):
    """
    View to securely update a user's mobile number using Firebase OTP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Pass the request context so the serializer can access the currently logged-in user
        serializer = UpdateMobileWithFirebaseSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            updated_user = serializer.save()
            
            return Response({
                "message": "Mobile number updated successfully.",
                "data": UserProfileSerializer(updated_user).data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserAddressCreateView(APIView):
    """
    API View to handle creating a new address for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserAddressSerializer(data=request.data)
        
        if serializer.is_valid():
            # Save the address and explicitly attach the authenticated user
            address = serializer.save(user=request.user)
            
            return Response(
                {
                    "message": "Address added successfully",
                    "data": UserAddressSerializer(address).data
                },
                status=status.HTTP_201_CREATED
            )
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Logout view
class CustomLogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')

        if refresh_token is None:
            return Response({"error": "Refresh token is missing"}, status=status.HTTP_404_NOT_FOUND)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"error": "Invalid Refresh token"}, status=status.HTTP_404_NOT_FOUND)

        response = Response(
            {"message": "Logout successfully"}, status=status.HTTP_200_OK)
        response.delete_cookie("refresh_token")
        return response


class CheckMobileAvailabilityView(APIView):
    """
    Checks if a mobile number is already taken before triggering Firebase OTP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        if not mobile_number:
            return Response({"error": "mobile_number is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        
        # Check Uniqueness Constraints
        if user.restaurant:
            exists = CustomUserModel.objects.filter(
                restaurant=user.restaurant, 
                mobile_number=mobile_number
            ).exclude(id=user.id).exists()
        else:
            exists = CustomUserModel.objects.filter(
                restaurant__isnull=True, 
                mobile_number=mobile_number
            ).exclude(id=user.id).exists()

        if exists:
            return Response({
                "available": False, 
                "message": "This mobile number is already registered at this restaurant."
            }, status=status.HTTP_200_OK)
        
        return Response({"available": True}, status=status.HTTP_200_OK)
    


# ======================================================================================================
# 🔹 Restaurant-admin views
# ======================================================================================================

class RestaurantAdminEmployeeViewSet(ModelViewSet):
    serializer_class = EmployeeReadSerializer
    lookup_field     = "public_id"
    pagination_class = StandardResultsSetPagination
    filterset_class  = EmployeeFilter            
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "username",
        "first_name",
        "email",
        "mobile_number",
    ]

    ordering_fields = [
        "username",
        "first_name",
        "email",
        "created_at",
        "updated_at",
    ]

    ordering = ["-created_at"]

    # ----------------------------
    # Restaurant Context
    # ----------------------------
    def get_restaurant(self):
        restaurant_id = self.request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise ValidationError("X-Restaurant-Id header missing")

        try:
            return Restaurant.objects.get(
                public_id=restaurant_id,
                is_active=True
            )
        except Restaurant.DoesNotExist:
            raise ValidationError("Invalid restaurant")

    # ----------------------------
    # Queryset
    # ----------------------------
    def get_queryset(self):
        restaurant = self.get_restaurant()

        return (
            CustomUserModel.objects
            .filter(
                restaurant=restaurant,
                is_staff=True
            )
            .select_related("restaurant")
        )

    # ----------------------------
    # Serializer Switching
    # ----------------------------
    def get_serializer_class(self):
        if self.action == "create":
            return EmployeeCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return EmployeeUpdateSerializer
        return EmployeeReadSerializer

    # ----------------------------
    # Inject Restaurant on Create
    # ----------------------------
    def perform_create(self, serializer):
        restaurant = self.get_restaurant()
        serializer.save(restaurant=restaurant)



# ==========================
# Only for employee login
# ==========================

class EmployeeLoginView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = EmployeeLoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.validated_data["user"]

        refresh_token = CustomTokenObtainPairSerializer.get_token(user)
        access_token = refresh_token.access_token

        response = Response(
            {
                "message": "User logged in successfully",
                "access_token": str(access_token),
            },
            status=status.HTTP_200_OK
        )

        response.set_cookie(
            key="refresh_token",
            value=str(refresh_token),
            httponly=True,
            secure=True,
            samesite="None",
            path="/",
        )

        return response


# Restornt admin User managemnt
class AdminCustomerManagementView(APIView):
    permission_classes = [IsAuthenticated]

    ALLOWED_ORDERING_FIELDS = [
        "created_at",
        "mobile_number",
        "email",
        "is_active"
    ]

    def get(self, request, user_id=None):
        restaurant = self._get_restaurant(request)
        if not restaurant:
            return Response({"error": "Invalid restaurant"}, status=400)

        # --------------------------
        # SINGLE USER
        # --------------------------
        if user_id:
            try:
                user = CustomUserModel.objects.get(
                    public_id=user_id,
                    restaurant=restaurant,
                    role="customer"
                )
                return Response(RestaurantAdminCustomerSerializer(user).data)
            except CustomUserModel.DoesNotExist:
                return Response({"error": "User not found"}, status=404)

        # --------------------------
        # BASE QUERYSET
        # --------------------------
        queryset = CustomUserModel.objects.filter(
            restaurant=restaurant,
            role="customer"
        )

        # --------------------------
        # 🔍 SEARCH
        # --------------------------
        search = request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(public_id__icontains=search)  |
                Q(mobile_number__icontains=search) |
                Q(email__icontains=search) |
                Q(username__icontains=search)
            )

        # --------------------------
        # 🔎 FILTER (Active / Blocked)
        # --------------------------
        is_active = request.GET.get("is_active")
        if is_active is not None:
            if is_active.lower() == "true":
                queryset = queryset.filter(is_active=True)
            elif is_active.lower() == "false":
                queryset = queryset.filter(is_active=False)

        # --------------------------
        # 📅 DATE RANGE
        # --------------------------
        date_after  = request.GET.get("created_at_after")
        date_before = request.GET.get("created_at_before")

        if date_after:
            try:
                queryset = queryset.filter(created_at__date__gte=date_after)
            except (ValueError, ValidationError):
                pass

        if date_before:
            try:
                queryset = queryset.filter(created_at__date__lte=date_before)
            except (ValueError, ValidationError):
                pass

        # --------------------------
        # ↕ SORTING
        # --------------------------
        ordering = request.GET.get("ordering", "-created_at")
        if ordering.lstrip("-") not in self.ALLOWED_ORDERING_FIELDS:
            ordering = "-created_at"
        queryset = queryset.order_by(ordering)

        # --------------------------
        # PAGINATION
        # --------------------------
        paginator          = StandardResultsSetPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer         = RestaurantAdminCustomerSerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)
    # --------------------------
    # UPDATE BLOCK / UNBLOCK
    # --------------------------
    def patch(self, request, user_id):
        restaurant = self._get_restaurant(request)
        if not restaurant:
            return Response({"error": "Invalid restaurant"}, status=400)

        try:
            user = CustomUserModel.objects.get(
                public_id=user_id,
                restaurant=restaurant,
                role="customer"
            )

            if "is_active" in request.data:
                user.is_active = request.data["is_active"]

            # Increment auth_version
            current_version = int(user.auth_version.lstrip("v"))
            user.auth_version = f"v{current_version + 1}"

            user.save()

            publish_user_updated_event(user=user)

            return Response({
                "message": "User status updated successfully",
                "is_active": user.is_active
            })

        except CustomUserModel.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
    

    
    def delete(self, request, user_id):
        restaurant = self._get_restaurant(request)
        if not restaurant:
            return Response({"error": "Invalid restaurant"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUserModel.objects.get(
                public_id=user_id,
                restaurant=restaurant,
                role="customer"
            )

            user.delete()

            return Response(
                {"message": "User deleted successfully"}, 
                status=status.HTTP_204_NO_CONTENT
            )

        except CustomUserModel.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    def _get_restaurant(self, request):
        restaurant_id = request.headers.get("X-Restaurant-Id")
        return Restaurant.objects.filter(
            public_id=restaurant_id,
            is_active=True
        ).first()



# For restaurent admin dashboard

class AdminCustomersStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant_id = request.headers.get("X-Restaurant-Id")

        if not restaurant_id:
            return Response(
                {"detail": "Restaurant context missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Base queryset (customers only)
        users = CustomUserModel.objects.filter(
            restaurant__public_id=restaurant_id,
            role="customer",
        )

        now = timezone.localtime()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        month_start = today_start.replace(day=1)

        stats = users.aggregate(
            total_users=Count("id"),

            active_users=Count(
                "id",
                filter=Q(is_active=True)
            ),

            inactive_users=Count(
                "id",
                filter=Q(is_active=False)
            ),

            today_users=Count(
                "id",
                filter=Q(created_at__gte=today_start)
            ),

            month_users=Count(
                "id",
                filter=Q(created_at__gte=month_start)
            ),
        )

        return Response({
            "total_users": stats["total_users"],
            "active_users": stats["active_users"],
            "inactive_users": stats["inactive_users"],
            "today_users": stats["today_users"],
            "month_users": stats["month_users"],
        })


class AdminPasswordResetOTPView(APIView):
    """
    Step 1: Request an OTP to be sent to the Restaurant Admin's email.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure the user exists and is specifically a restaurant admin
        user = CustomUserModel.objects.filter(email=email, role="restaurant-admin").first()
        
        if not user:
            return Response(
                {"error": "No active restaurant admin found with this email."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if not user.is_active:
            return Response({"error": "This account is blocked."}, status=status.HTTP_403_FORBIDDEN)

        # Generate a 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Store OTP in cache for 10 minutes (600 seconds)
        cache_key = f"admin_pwd_reset_otp_{email}"
        cache.set(cache_key, otp, timeout=600)

        # 2. Prepare the email arguments
        subject = "DineFlow - Admin Password Reset OTP"
        message = f"Hello {user.first_name or 'Admin'},\n\nYour OTP for password reset is: {otp}\n\nThis OTP is valid for 10 minutes. If you did not request this, please ignore this email."
        
        # 3. Fire and forget! Start the thread and move on immediately.
        email_thread = threading.Thread(
            target=send_email_background,
            args=(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        )
        email_thread.start()

        # The API responds instantly while the email is being sent in the background
        return Response({"message": "OTP sent successfully to your email."}, status=status.HTTP_200_OK)



class AdminPasswordResetConfirmView(APIView):
    """
    Step 2: Verify the OTP and set the new password.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp_entered = request.data.get("otp")
        new_password = request.data.get("new_password")

        # Basic validation
        if not all([email, otp_entered, new_password]):
            return Response(
                {"error": "Email, otp, and new_password are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate OTP from cache
        cache_key = f"admin_pwd_reset_otp_{email}"
        cached_otp = cache.get(cache_key)

        if not cached_otp or str(cached_otp) != str(otp_entered):
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch the user
        user = CustomUserModel.objects.filter(email=email, role="restaurant-admin").first()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Change the password
        user.set_password(new_password)
        
        # Increment auth_version to invalidate all existing tokens (Log out from all devices)
        current_version = int(user.auth_version.lstrip("v"))
        user.auth_version = f"v{current_version + 1}"
        
        user.save()

        # Delete the OTP from cache so it cannot be reused
        cache.delete(cache_key)

        return Response({"message": "Password has been successfully changed."}, status=status.HTTP_200_OK)
    

class AdminProfileUpdateView(APIView):
    """
    Allows a Restaurant Admin to update their personal details, including email.
    Requires verifying their current password.
    Only allows PATCH requests.
    """
    http_method_names = ['patch']
    permission_classes = [permissions.AllowAny] 

    def patch(self, request, *args, **kwargs):
        user_id = request.headers.get("X-User-Id")
        
        if not user_id:
            return Response(
                {"error": "X-User-Id header missing. Unauthorized."}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

        user = CustomUserModel.objects.filter(public_id=user_id, role="restaurant-admin").first()
        
        if not user:
            return Response(
                {"error": "Admin user not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminProfileUpdateSerializer(
            user, 
            data=request.data, 
            partial=True, 
            context={'user': user}
        )

        if serializer.is_valid():
            # If the user changed their email, it will be saved here automatically
            serializer.save()
            
            return Response({
                "message": "Admin profile updated successfully.",
                "admin_details": {
                    "first_name": user.first_name,
                    "email": user.email,  # Returns the fresh, potentially updated email
                    "created_at": user.created_at,
                    "updated_at": user.updated_at
                    
                }
            }, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =============================
# 🔹 Super-admin views
# =============================

class SuperAdminLoginView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SuperAdminLoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.validated_data["user"]

        refresh_token = CustomTokenObtainPairSerializer.get_token(user)
        access_token = refresh_token.access_token

        response = Response(
            {
                "message": "SuperAdmin logged in successfully",
                "access_token": str(access_token),
            },
            status=status.HTTP_200_OK
        )

        response.set_cookie(
            key="refresh_token",
            value=str(refresh_token),
            httponly=True,
            secure=True,
            samesite="None",
            path="/",
        )

        return response


# For manageing the satff of the restorent

class SuperAdminRestaurantStaffView(APIView):

    pagination_class = StandardResultsSetPagination

    def get(self, request):

        restaurants = Restaurant.objects.all().prefetch_related("users")

        role = request.GET.get("role")
        is_active = request.GET.get("is_active")
        search = request.GET.get("search")

        # -------------------------
        # SEARCH (Restaurant + Staff)
        # -------------------------
        if search:
            restaurants = restaurants.filter(
                Q(name__icontains=search) |
                Q(public_id__icontains=search) |
                Q(users__public_id__icontains=search) |
                Q(users__mobile_number__icontains=search)
            ).distinct()

        # -------------------------
        # SORTING
        # -------------------------
        ordering = request.GET.get("ordering", "name")

        allowed_sort = ["name", "-name", "created_at", "-created_at"]

        if ordering in allowed_sort:
            restaurants = restaurants.order_by(ordering)

        # -------------------------
        # PAGINATION
        # -------------------------
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(restaurants, request)

        data = []

        for restaurant in page:

            users = restaurant.users.filter(
                role__in=["restaurant-admin", "waiter", "kitchen-staff"],
                is_staff=True
            )

            # role filter
            if role:
                users = users.filter(role=role)

            # active filter
            if is_active:
                users = users.filter(is_active=is_active.lower() == "true")

            admins = users.filter(role="restaurant-admin")
            waiters = users.filter(role="waiter")
            kitchen = users.filter(role="kitchen-staff")

            data.append({
                "restaurant_id": restaurant.public_id,
                "restaurant_name": restaurant.name,

                "admins": StaffSerializer(admins, many=True).data,
                "waiters": StaffSerializer(waiters, many=True).data,
                "kitchen_staff": StaffSerializer(kitchen, many=True).data,

                "total_staff": users.count(),
                "total_waiters": waiters.count(),
                "total_kitchen": kitchen.count(),
            })

        return paginator.get_paginated_response(data)
    


# For blocking all the staff in the restaurent


class BlockRestaurantStaffView(APIView):

    def patch(self, request, restaurant_public_id):

        is_active = request.data.get("is_active")

        if is_active is None:
            return Response(
                {"error": "is_active field required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            restaurant = Restaurant.objects.get(public_id=restaurant_public_id)
        except Restaurant.DoesNotExist:
            return Response(
                {"error": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        users = CustomUserModel.objects.filter(
            restaurant=restaurant,
            role__in=["restaurant-admin", "waiter", "kitchen-staff"],
            is_staff=True
        )

        updated_count = users.update(is_active=is_active)

        return Response({
            "message": "Restaurant staff updated successfully",
            "restaurant_id": restaurant.public_id,
            "updated_staff": updated_count,
            "is_active": is_active
        })
    

# To block a sigle staff 

class BlockSingleStaffView(APIView):

    def patch(self, request, public_id):

        is_active = request.data.get("is_active")

        if is_active is None:
            return Response(
                {"error": "is_active field required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = CustomUserModel.objects.get(
                public_id=public_id,
                role__in=["restaurant-admin", "waiter", "kitchen-staff"]
            )
        except CustomUserModel.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        user.is_active = is_active
        user.save(update_fields=["is_active"])

        return Response({
            "message": "Staff status updated",
            "user_id": user.public_id,
            "is_active": user.is_active
        })
    

# For managing all the customers of the platform


class SuperAdminCustomerManagementView(APIView):

    permission_classes = [IsAuthenticated]

    ALLOWED_ORDERING_FIELDS = [
        "created_at",
        "mobile_number",
        "email",
        "is_active"
    ]

    def get(self, request, user_id=None):

        # ----------------------------
        # SINGLE CUSTOMER
        # ----------------------------
        if user_id:
            try:
                user = CustomUserModel.objects.select_related(
                    "restaurant"
                ).get(
                    public_id=user_id,
                    role="customer"
                )

                return Response(
                    RestaurantAdminCustomerSerializer(user).data
                )

            except CustomUserModel.DoesNotExist:
                return Response(
                    {"error": "Customer not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

        # ----------------------------
        # BASE QUERYSET
        # ----------------------------
        queryset = CustomUserModel.objects.filter(
            role="customer",is_staff = False
        ).select_related("restaurant")

        # ----------------------------
        # 🔍 SEARCH
        # ----------------------------
        search = request.GET.get("search")

        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(public_id__icontains=search) |
                Q(mobile_number__icontains=search) |
                Q(email__icontains=search) |
                Q(username__icontains=search) |
                Q(restaurant__name__icontains=search) |
                Q(restaurant__public_id__icontains=search)
            )

        # ----------------------------
        # 🔎 ACTIVE FILTER
        # ----------------------------
        is_active = request.GET.get("is_active")

        if is_active is not None:

            if is_active.lower() == "true":
                queryset = queryset.filter(is_active=True)

            elif is_active.lower() == "false":
                queryset = queryset.filter(is_active=False)

        # ----------------------------
        # 📅 DATE FILTER
        # ----------------------------
        created_after = request.GET.get("created_at_after")
        created_before = request.GET.get("created_at_before")

        if created_after:
            queryset = queryset.filter(
                created_at__date__gte=created_after
            )

        if created_before:
            queryset = queryset.filter(
                created_at__date__lte=created_before
            )

        # ----------------------------
        # ↕ SORTING
        # ----------------------------
        ordering = request.GET.get("ordering", "-created_at")

        if ordering.lstrip("-") not in self.ALLOWED_ORDERING_FIELDS:
            ordering = "-created_at"

        queryset = queryset.order_by(ordering)

        # ----------------------------
        # 📄 PAGINATION
        # ----------------------------
        paginator = StandardResultsSetPagination()

        page = paginator.paginate_queryset(queryset, request)

        serializer = SuperAdminCustomerSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    # ----------------------------
    # BLOCK / UNBLOCK CUSTOMER
    # ----------------------------
    def patch(self, request, user_id):

        try:
            user = CustomUserModel.objects.get(
                public_id=user_id,
                role="customer"
            )

            if "is_active" in request.data:
                user.is_active = request.data["is_active"]

            # increment auth version → logout user sessions
            current_version = int(user.auth_version.lstrip("v"))
            user.auth_version = f"v{current_version + 1}"

            user.save()

            return Response({
                "message": "Customer status updated successfully",
                "is_active": user.is_active
            })

        except CustomUserModel.DoesNotExist:
            return Response(
                {"error": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND
            )