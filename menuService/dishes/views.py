from rest_framework.viewsets import ModelViewSet
from .models import Dish
from .serializers import DishReadSerializer, DishWriteSerializer
from drf_spectacular.utils import extend_schema
from django.core.cache import cache
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from dish_reviews.models import DishReview
from .models import Dish


# For helth checks for ngninx

def get_dish_cache_version(restaurant_id):
    return cache.get_or_set(
        f"dishes:version:{restaurant_id}",
        1,
        timeout=None
    )


def bump_dish_cache_version(restaurant_id):
    key = f"dishes:version:{restaurant_id}"

    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=None)


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


# ------------------------
# Customer views
# ------------------------
@extend_schema(tags=["Dishes"])
class DishesListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = DishReadSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    # 🔍 search
    search_fields = [
        "name",
        "description",
    ]

    # 🧩 filters
    filterset_fields = {
        "category__public_id": ["exact"],
        "is_veg": ["exact"],
        "is_spicy": ["exact"],
        "is_popular": ["exact"],
        "is_quick_bites": ["exact"],
        "is_trending": ["exact"],
        "is_available": ["exact"],
        "price": ["gte", "lte"],
    }

    # ↕️ sorting
    ordering_fields = [
        "priority",
        "price",
        "created_at",
        "total_orders",
    ]


    def get_queryset(self):
        return (
            Dish.objects
            .filter(is_available=True)
            .select_related("category")
            .prefetch_related("images")
            .order_by('-priority', 'public_id')
        )

    def list(self, request, *args, **kwargs):
        query_string = request.query_params.urlencode() or "all"
        tenant_id = request.headers.get("X-Restaurant-Id")

        version = get_dish_cache_version(tenant_id)
        cache_key = f"dishes:list:{tenant_id}:v{version}:{query_string}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=60 * 5)
        return response


@extend_schema(tags=["Dishes"])
class DishDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, public_id):
        dish = (
            Dish.objects
            .select_related("category")
            .prefetch_related("images")
            .get(public_id=public_id)
        )

        serializer = DishReadSerializer(dish)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ------------------------
# Waiter views
# ------------------------

@extend_schema(tags=["Waiter Dishes"])
class WaiterDishesListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = DishReadSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = ["name", "description"]

    filterset_fields = {
        "category__public_id": ["exact"],
        "is_veg": ["exact"],
        "is_spicy": ["exact"],
        "is_popular": ["exact"],
        "is_quick_bites": ["exact"],
        "is_trending": ["exact"],
        "is_available": ["exact"],
        "price": ["gte", "lte"],
    }

    ordering_fields = [
        "priority",
        "price",
        "created_at",
        "total_orders",
    ]

    def get_queryset(self):
        return (
            Dish.objects
            .select_related("category")
            .prefetch_related("images")
            .order_by('-priority', 'public_id')
        )

    def list(self, request, *args, **kwargs):
        query_string = request.query_params.urlencode() or "all"
        tenant_id = request.headers.get("X-Restaurant-Id")

        version = get_dish_cache_version(tenant_id)
        cache_key = f"dishes:waiter:{tenant_id}:v{version}:{query_string}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=60 * 5)
        return response


@extend_schema(tags=["Dishes"])
class WaiterDishDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, public_id):
        dish = (
            Dish.objects
            .select_related("category")
            .prefetch_related("images")
            .get(public_id=public_id)
        )

        serializer = DishReadSerializer(dish)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ------------------------
# Restaurent Admin views
# ------------------------


@extend_schema(tags=["AdminDish Management"])
class AdminDishViewSet(ModelViewSet):
    permission_classes = []
    authentication_classes = []
    lookup_field = "public_id"

    # --------------------------------
    # Queryset
    # --------------------------------
    def get_queryset(self):
        return (
            Dish.objects
            .select_related("category")
            .prefetch_related("images")
            .order_by('-priority', 'public_id')
        )

    # --------------------------------
    # Serializer selection
    # --------------------------------
    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return DishReadSerializer
        return DishWriteSerializer

    # --------------------------------
    # Bulk support (many=True)
    # --------------------------------
    def get_serializer(self, *args, **kwargs):
        data = kwargs.get("data")
        if isinstance(data, list):
            kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

    # --------------------------------
    # Context
    # --------------------------------
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    # --------------------------------
    # FILTERS / SEARCH / SORT
    # --------------------------------
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    # 🔍 search
    search_fields = [
        "name",
        "description",
        "public_id"
    ]

    # 🧩 filters
    filterset_fields = {
        "category__public_id": ["exact"],
        "is_veg": ["exact"],
        "is_spicy": ["exact"],
        "is_popular": ["exact"],
        "is_quick_bites": ["exact"],
        "is_trending": ["exact"],
        "is_available": ["exact"],
        "price": ["gte", "lte"],
    }

    # ↕️ sorting
    ordering_fields = [
        "priority",
        "price",
        "created_at",
        "total_orders",
    ]

    ordering = ["-priority", "-created_at"]

    # --------------------------------
    # Create
    # --------------------------------
    def perform_create(self, serializer):
        restaurant_id = self.request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise ValidationError("X-Restaurant-Id header missing")

        serializer.save(restaurant_id=restaurant_id)

        # bump cache once (bulk safe)
        bump_dish_cache_version(restaurant_id)

    # --------------------------------
    # Update
    # --------------------------------
    def perform_update(self, serializer):
        dish = serializer.save()
        bump_dish_cache_version(dish.restaurant_id)

    # --------------------------------
    # Delete
    # --------------------------------
    def perform_destroy(self, instance):
        restaurant_id = instance.restaurant_id
        instance.delete()
        bump_dish_cache_version(restaurant_id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        read_serializer = DishReadSerializer(
            serializer.instance,
            context=self.get_serializer_context()
        )

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        read_serializer = DishReadSerializer(
            serializer.instance,
            context=self.get_serializer_context()
        )

        return Response(read_serializer.data)


class AdminCategoryDishStatsView(APIView):

    permission_classes = []
    authentication_classes = []

    def get(self, request):

        qs = (
            Dish.objects
            .values(
                "category__public_id",
                "category__name",
            )
            .annotate(
                dish_count=Count("id")
            )
            .order_by("-dish_count")
        )

        data = [
            {
                "category_id": item["category__public_id"],
                "category_name": item["category__name"],
                "dish_count": item["dish_count"],
            }
            for item in qs
        ]

        return Response(data, status=status.HTTP_200_OK)


# Dish status for dashboard


class AdminDishStatsView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):

        # -----------------------------------
        # DISH BASE QUERYSET
        # -----------------------------------
        dishes = Dish.objects.all()

        # -----------------------------------
        # REVIEW BASE QUERYSET
        # -----------------------------------
        reviews = DishReview.objects.all()

        today_start = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # -----------------------------------
        # AGGREGATIONS
        # -----------------------------------
        dish_stats = dishes.aggregate(
            total_dishes=Count("id"),
            active_dishes=Count("id", filter=Q(is_available=True)),
            inactive_dishes=Count("id", filter=Q(is_available=False)),
        )

        review_stats = reviews.aggregate(
            total_reviews=Count("id"),
            today_reviews=Count(
                "id",
                filter=Q(created_at__gte=today_start)
            )
        )

        return Response({
            "total_dishes": dish_stats["total_dishes"],
            "active_dishes": dish_stats["active_dishes"],
            "inactive_dishes": dish_stats["inactive_dishes"],
            "total_reviews": review_stats["total_reviews"],
            "today_reviews": review_stats["today_reviews"],
        })


# ======================
# internal API for AI
# ======================


@extend_schema(tags=["AI Dishes"])
class AIDishListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        tenant_id = request.headers.get("X-Restaurant-Id")

        if not tenant_id:
            return Response(
                {"error": "X-Restaurant-Id header missing"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ Cache
        version = get_dish_cache_version(tenant_id)
        cache_key = f"dishes:ai:{tenant_id}:v{version}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        # ✅ Query
        queryset = (
            Dish.objects
            .filter(is_available=True)
            .select_related("category")
            .prefetch_related("images")
        )

        serializer = DishReadSerializer(queryset, many=True)
        data = serializer.data

        cache.set(cache_key, data, timeout=60 * 5)

        return Response(data, status=status.HTTP_200_OK)
