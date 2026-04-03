from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdminCategoryViewSet,CategoryListView,WaiterCategoryListView

router = DefaultRouter()

router.register(
    r"categories",
    AdminCategoryViewSet,
    basename="admin-categories"
)

urlpatterns = [
    path("restaurant-admin/", include(router.urls)),
    path("customer/categories/", CategoryListView.as_view(), name="category-list-view"),
    path("waiter/categories/", CategoryListView.as_view(), name="WaiterCategory-list-view"),
]