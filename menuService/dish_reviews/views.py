from rest_framework.generics import ListAPIView
from drf_spectacular.utils import extend_schema
from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from .models import DishReview
from .serializers import DishesReviewSerializer,AdminDishReviewSerializer
from .filters import DishReviewFilter
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction




@extend_schema(tags=["DishReview"])
class DishReviewListView(ListAPIView):
    serializer_class = DishesReviewSerializer
    permission_classes = []
    authentication_classes=[] 

    def get_queryset(self):
        dish_id = self.kwargs["dish_id"]
        return DishReview.objects.filter(dish__public_id=dish_id)
    



@extend_schema(tags=["DishReview"])
class DishReviewCreateView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        user_name = request.headers.get("X-User-Name")
        user_id = request.headers.get("X-User-Id")
        restaurant_id = request.headers.get("X-Restaurant-Id")

        if not user_name:
            return Response(
                {"detail": "X-User-Name header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_id:
            return Response(
                {"detail": "X-User-Id header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not restaurant_id:
            return Response(
                {"detail": "X-Restaurant-Id header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DishesReviewSerializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            review = serializer.save(
                user_name=user_name,
                user_public_id=user_id,
                restaurant_id=restaurant_id
            )

        return Response(
            {
                "message": "Review created successfully",
                "review_id": review.public_id,
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================
# Admin Views
# ============================================


@extend_schema(tags=["Admin DishReview"])
class AdminDishReviewViewSet(ModelViewSet):
    queryset = DishReview.objects.select_related("dish")
    serializer_class = AdminDishReviewSerializer
    permission_classes = []
    authentication_classes = []
    lookup_field = "public_id"

    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_class = DishReviewFilter          

    search_fields = ["user_name", "comment", "user_public_id"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at"]
