import requests
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ModelViewSet
from .serializers import SuperAdminRestaurantManagementSerializer
from .serializers import RestaurantAdminTableSerializer, RestaurantAdminZoneSerializer
from restaurant.models import Table, RestaurantZone, Restaurant
from rest_framework.response import Response
from rest_framework import status
from .serializers import RestaurantAdminCreateSerializer, RestaurantUserSerializer, WaiterZoneSerializer, RestaurantAdminRestaurantSerializer,WaiterTableSerializer
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Q
from .pagination import Pagination
from kafka.table_producer import publish_table_upsert_event
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count, Q
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.generics import RetrieveUpdateAPIView
from .filters import RestaurantFilter

# =============================
# 🔹 Super-admin views
# =============================

class SuperAdminRestaurantManagementView(ModelViewSet):
    queryset = Restaurant.objects.all().order_by("-created_at")
    serializer_class = SuperAdminRestaurantManagementSerializer
    pagination_class = Pagination

    lookup_field = "public_id"

    # ----------------------------
    # Filters / Search / Ordering
    # ----------------------------
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    # Exact field filtering
    filterset_class = RestaurantFilter

    # Search fields
    search_fields = [
        "name",
        "email",
        "phone",
        "public_id",
        "address",
    ]

    # Ordering fields
    ordering_fields = [
        "name",
        "created_at",
        "updated_at",
        "is_active",
    ]

    ordering = ["-created_at"]

    # --------------------------------
    # Create Restaurant + Admin
    # --------------------------------
    def create(self, request, *args, **kwargs):
        restaurant_serializer = self.get_serializer(data=request.data)
        restaurant_serializer.is_valid(raise_exception=True)

        admin_data = request.data.get("admin")
        if not admin_data:
            raise ValidationError(
                {"admin": "Restaurant admin details are required"}
            )

        with transaction.atomic():

            # 1️⃣ Create Restaurant
            restaurant = restaurant_serializer.save()
            tenant_id = restaurant.public_id

            # 2️⃣ Create Restaurant Admin
            admin_serializer = RestaurantAdminCreateSerializer(
                data=admin_data,
                context={"restaurant_id": tenant_id},
            )

            admin_serializer.is_valid(raise_exception=True)
            admin_user = admin_serializer.save()

            # 3️⃣ Provision services
            provisioned_services = []

            services_map = [
                ("Order", settings.ORDER_SERVICE_TENANT_PROVISION_URL),
                ("Menu", settings.MENU_SERVICE_TENANT_PROVISION_URL),
                ("Kitchen", settings.KITCHEN_SERVICE_TENANT_PROVISION_URL),
                ("Cart", settings.CART_SERVICE_TENANT_PROVISION_URL),
                ("Notification", settings.NOTIFICATION_SERVICE_TENANT_PROVISION_URL),
            ]

            try:
                for service_name, url in services_map:

                    resp = requests.post(
                        url,
                        json={"tenant_id": tenant_id},
                        timeout=10,
                    )

                    if resp.status_code not in (200, 201):
                        raise Exception(
                            f"{service_name} service failed: {resp.text}"
                        )

                    provisioned_services.append((service_name, url))

            except Exception as e:

                # rollback remote services
                for service_name, url in provisioned_services:
                    try:
                        requests.delete(
                            url,
                            json={"tenant_id": tenant_id},
                            timeout=5,
                        )
                    except Exception:
                        pass

                raise ValidationError(
                    {
                        "tenant_provisioning":
                        f"System Error: {str(e)}. Changes rolled back."
                    }
                )

        return Response(
            {
                "restaurant": SuperAdminRestaurantManagementSerializer(
                    restaurant
                ).data,
                "admin_user": {
                    "id": admin_user.id,
                    "email": admin_user.email,
                    "mobile_number": admin_user.mobile_number,
                    "role": admin_user.role,
                    "is_staff": admin_user.is_staff,
                },
                "status": "SUCCESS",
            },
            status=status.HTTP_201_CREATED,
        )


# =============================
# 🔹 Restaurant-admin views
# =============================


class RestaurantAdminRestaurantView(RetrieveUpdateAPIView):

    serializer_class = RestaurantAdminRestaurantSerializer
    lookup_field = "public_id"

    def get_object(self):

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



# Used to create the zone of the restaurant

class RestaurantAdminZoneViewSet(ModelViewSet):
    serializer_class = RestaurantAdminZoneSerializer
    lookup_field = "public_id"

    def get_restaurant(self):
        restaurant_id = self.request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise ValidationError({"error": "X-Restaurant-Id header missing"})

        try:
            return Restaurant.objects.get(
                public_id=restaurant_id,
                is_active=True
            )
        except Restaurant.DoesNotExist:
            raise ValidationError({"error": "Invalid restaurant"})

    def get_queryset(self):
        restaurant = self.get_restaurant()
        return RestaurantZone.objects.filter(
            restaurant=restaurant
        ).select_related("restaurant")

    def create(self, request, *args, **kwargs):
        data = request.data
        is_many = isinstance(data, list)

        serializer = self.get_serializer(data=data, many=is_many)
        serializer.is_valid(raise_exception=True)

        # Securely inject the restaurant
        restaurant = self.get_restaurant()
        serializer.save(restaurant=restaurant)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_destroy(self, instance):
        instance.delete()


# ---------------------------------------------------------
# Table ViewSet
# ---------------------------------------------------------
class RestaurantAdminTableViewSet(ModelViewSet):
    serializer_class = RestaurantAdminTableSerializer
    lookup_field = "public_id"
    # pagination_class = Pagination # Ensure this is imported

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        "is_occupied": ["exact"],
        "is_active": ["exact"],
        "is_reserved_manual": ["exact"],
        "table_type": ["exact"],
        "zone__public_id": ["exact"],
        "capacity": ["gte", "lte"],
    }
    search_fields = ["table_number", "public_id"]
    ordering_fields = ["table_number", "capacity", "created_at", "updated_at", "is_occupied"]
    ordering = ["table_number"]

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

    def get_queryset(self):
        restaurant = self.get_restaurant()
        return Table.objects.filter(
            restaurant=restaurant
        ).select_related("restaurant", "zone")

    def create(self, request, *args, **kwargs):
        data = request.data
        is_many = isinstance(data, list)

        serializer = self.get_serializer(data=data, many=is_many)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        restaurant = self.get_restaurant()
        
        # Securely inject the restaurant
        instances = serializer.save(restaurant=restaurant)

        if isinstance(instances, list):
            for table in instances:
                transaction.on_commit(lambda t=table: publish_table_upsert_event(table=t))
        else:
            transaction.on_commit(lambda: publish_table_upsert_event(table=instances))

    def perform_update(self, serializer):
        table = serializer.save()
        transaction.on_commit(lambda: publish_table_upsert_event(table=table))

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        restaurant = self.get_restaurant()
        qs = Table.objects.filter(restaurant=restaurant)

        stats = qs.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
            occupied=Count("id", filter=Q(is_occupied=True)),
            available=Count("id", filter=Q(is_active=True, is_occupied=False)),
            reserved=Count("id", filter=Q(is_reserved_manual=True)),
            standard_tables=Count("id", filter=Q(table_type="standard")),
            counter_tables=Count("id", filter=Q(table_type="counter")),
            delivery_tables=Count("id", filter=Q(table_type="delivery")),
        )
        return Response(stats)

# ========================
# users view for detail of the Restaurant
# ==========================


class RestaurantDetailsView(APIView):

    def get(self, request):

        restaurant_id = request.headers.get("X-Restaurant-Id")

        if not restaurant_id:
            return Response(
                {"error": "Restaurant ID header missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            restaurant = Restaurant.objects.get(
                public_id=restaurant_id,
                is_active=True
            )
        except Restaurant.DoesNotExist:
            return Response(
                {"error": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = RestaurantUserSerializer(restaurant)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =============================
# 🔹WAITER views
# =============================

# For listing all the zone in the waiter side

class WaiterZoneListView(APIView):

    def get(self, request):
        restaurant_id = request.headers.get("X-Restaurant-Id")

        if not restaurant_id:
            return Response(
                {"error": "Restaurant ID header missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        zones = RestaurantZone.objects.filter(
            restaurant__public_id=restaurant_id
        ).order_by("name")

        serializer = WaiterZoneSerializer(zones, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


# All tables avilabe and its statuse

class WaiterTableListView(APIView):

    def get(self, request):
        restaurant_id = request.headers.get("X-Restaurant-Id")
        zone_id = request.query_params.get("zone")
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search")
        table_type = request.query_params.get("table_type")

        if not restaurant_id:
            return Response(
                {"error": "Restaurant ID header missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        tables = Table.objects.filter(
            restaurant__public_id=restaurant_id,
            is_active=True
        )

        # 🔹 Filter by zone
        if zone_id:
            if not RestaurantZone.objects.filter(
                public_id=zone_id,
                restaurant__public_id=restaurant_id
            ).exists():
                return Response(
                    {"error": "Invalid zone"},
                    status=status.HTTP_404_NOT_FOUND
                )

            tables = tables.filter(zone__public_id=zone_id)

        # 🔹 Filter by table type
        if table_type:
            tables = tables.filter(table_type=table_type)

        now = timezone.now()

        # 🔹 Status Filtering
        if status_filter == "available":
            tables = tables.filter(
                is_occupied=False,
                is_reserved_manual=False
            ).exclude(
                reservations__status__in=["pending", "confirmed"],
                reservations__end_time__gte=now
            )

        elif status_filter == "occupied":
            tables = tables.filter(is_occupied=True)

        elif status_filter == "reserved":
            tables = tables.filter(
                reservations__status__in=["pending", "confirmed"],
                reservations__end_time__gte=now
            )

        # 🔹 Search
        if search:
            tables = tables.filter(
                Q(table_number__icontains=search) |
                Q(reservations__user__username__icontains=search)
            )

        tables = tables.select_related(
            "zone").distinct().order_by("table_number")

        paginator = Pagination()
        paginated_tables = paginator.paginate_queryset(tables, request)

        serializer = WaiterTableSerializer(paginated_tables, many=True)
        return paginator.get_paginated_response(serializer.data)


# check if the tabel is free or not
class WaiterCheckTableOccupiedView(APIView):

    def get(self, request, table_id):
        try:
            table = Table.objects.get(public_id=table_id)
        except Table.DoesNotExist:
            return Response(
                {"error": "Table does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if table.is_occupied:
            return Response(
                {"error": "Table is occupied by another user", "is_occupied": True},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"message": "Table is available", "is_occupied": False},
            status=status.HTTP_200_OK,
        )
