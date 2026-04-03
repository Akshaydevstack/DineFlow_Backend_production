from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SuperAdminRestaurantManagementView,
    RestaurantAdminZoneViewSet,   
    RestaurantAdminTableViewSet,
    RestaurantDetailsView,
    WaiterTableListView,
    WaiterZoneListView,
    WaiterCheckTableOccupiedView,
    RestaurantAdminRestaurantView
)

router = DefaultRouter()

# ==================================
# 🔹 Super Admin Routes
# ==================================
router.register(
    r'super-admin/restaurants',
    SuperAdminRestaurantManagementView,
    basename='superadmin-restaurants'
)

# ==================================
# 🔹 Restaurant Admin Routes 
# ==================================
router.register(
    r'restaurant-admin/zones',
    RestaurantAdminZoneViewSet,
    basename='restaurant-admin-zones'
)

router.register(
    r'restaurant-admin/tables',
    RestaurantAdminTableViewSet,
    basename='restaurant-admin-tables'
)


urlpatterns = [
    path('', include(router.urls)),
    path('customer/restaurant-details/',RestaurantDetailsView.as_view(), name='Restorent Details'),
    path('waiter/zones/',WaiterZoneListView.as_view(), name='zone list Details'),
    path('waiter/table/',WaiterTableListView.as_view(), name='table list  Details'),
    path('waiter/check-tabel-status/<str:table_id>/',WaiterCheckTableOccupiedView.as_view(), name='Check if the table is occupied'),
    path("restaurant-admin/restaurant/",RestaurantAdminRestaurantView.as_view(),name="restaurant-admin-restaurant"),
]