from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DishReviewCreateView,
    DishReviewListView,
    AdminDishReviewViewSet,
)

# 🔹 Admin Router
router = DefaultRouter()
router.register(
    r"reviews",
    AdminDishReviewViewSet,
    basename="admin-reviews"
)

urlpatterns = [
    # Customer Routes
    path("customer/reviews/", DishReviewCreateView.as_view(), name="review-create"),
    path("customer/reviews/<str:dish_id>/", DishReviewListView.as_view(), name="review-by-dish"),

    # Admin Routes
    path("restaurant-admin/", include(router.urls)),
]