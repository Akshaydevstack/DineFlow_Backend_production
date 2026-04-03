from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminDishViewSet,
    AdminCategoryDishStatsView,
    AdminDishStatsView,
    DishesListView,
    DishDetailView,
    WaiterDishesListView,
    WaiterDishDetailView,
    AIDishListView
)

router = DefaultRouter()
router.register(
    r"dishes",
    AdminDishViewSet,
    basename="admin-dish"
)

urlpatterns = [

    # =========================
    # 🔐 internal Routes for AI
    # =========================

    path(
        "internal/ai/dishes/list/",
        AIDishListView.as_view(),
        name="ai-dish-list for recommentations"
    ),

    # =========================
    # 🔐 Restaurant Admin Routes
    # =========================
    path(
        "restaurant-admin/category-stats/",
        AdminCategoryDishStatsView.as_view(),
        name="admin-category-dish-stats",
    ),
     path(
        "restaurant-admin/dish-stats/",
        AdminDishStatsView.as_view(),
        name="admin-category-dish-stats",
    ),
    path(
        "restaurant-admin/",
        include(router.urls),
    ),

    # =========================
    # 👤 Customer Routes
    # =========================
    path(
        "customer/dishes/",
        DishesListView.as_view(),
        name="customer-dish-list",
    ),
    path(
        "customer/dishe/<str:public_id>/",
        DishDetailView.as_view(),
        name="customer-dish-detail",
    ),

    # =========================
    # 🧑‍🍳 Waiter Routes
    # =========================
    path(
        "waiter/dishes/",
        WaiterDishesListView.as_view(),
        name="waiter-dish-list",
    ),
    path(
        "waiter/dishe/<str:public_id>/",
        WaiterDishDetailView.as_view(),
        name="waiter-dish-detail",
    ),
]