from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    UserRegistrationView,
    EmployeeLoginView,
    CustomLogoutView,
    CookieTokenRefreshView,
    ValidateScanView,
    RestaurantAdminEmployeeViewSet,
    UserLoginWithFirebaseView,
    SuperAdminLoginView,
    AdminCustomerManagementView,
    AdminCustomersStatsView,
    SuperAdminRestaurantStaffView,
    BlockRestaurantStaffView,
    BlockSingleStaffView,
    SuperAdminCustomerManagementView,
    UserProfileView,
    UserAddressCreateView
)

# ==================================
# 🔹 DRF Router for ViewSets
# ===================================
router = DefaultRouter()
router.register(
    r"restaurant-admin/employee-management",
    RestaurantAdminEmployeeViewSet,
    basename="restaurant-admin-employe",
)

urlpatterns = [

    # =============================
    # 🔹 Super Admin
    # =============================
    path(
        "superadmin/login/",
        SuperAdminLoginView.as_view(),
        name="superadmin-login",
    ),

    path(
        "super-admin/restaurants/staff/",
        SuperAdminRestaurantStaffView.as_view()
    ),

    path(
        "super-admin/restaurants/<str:restaurant_public_id>/block-staff/",
        BlockRestaurantStaffView.as_view()
    ),

    path(
        "super-admin/staff/<str:public_id>/block/",
        BlockSingleStaffView.as_view()
    ),
    path(
        "super-admin/customers/",
        SuperAdminCustomerManagementView.as_view(),
        name="superadmin-customer-list"
    ),

    # Get single customer / block-unblock
    path(
        "super-admin/customers/<str:user_id>/",
        SuperAdminCustomerManagementView.as_view(),
        name="superadmin-customer-details and management"
    ),

    # =============================
    # 🔹 User Auth
    # =============================
    path(
        "register-user/",
        UserRegistrationView.as_view(),
        name="register-user",
    ),

    path(
        "restaurant-user-login/",
        EmployeeLoginView.as_view(),
        name="employee-login",
    ),

    path(
        "login-firebase-user/",
        UserLoginWithFirebaseView.as_view(),
        name="login-firebase-user",
    ),

    path(
        "logout-user/",
        CustomLogoutView.as_view(),
        name="logout-user",
    ),

    path(
        "refreshtoken-user/",
        CookieTokenRefreshView.as_view(),
        name="refresh-user",
    ),

    path(
        "check-user/",
        ValidateScanView.as_view(),
        name="check-user",
    ),
    # To edit the user profile
    path(
        "customer/profile/",
        UserProfileView.as_view(),
        name="check-user",
    ),

    path("customer/addresses/",
         UserAddressCreateView.as_view(),
         name="create-address"),

    # =============================
    # 🔹 Restaurant Admin - Customers
    # =============================
    path(
        "restaurant-admin/customers/",
        AdminCustomerManagementView.as_view(),
        name="restaurant-admin-customer-list",
    ),

    path(
        "restaurant-admin/customers/<str:user_id>/",
        AdminCustomerManagementView.as_view(),
        name="restaurant-admin-customer-detail",
    ),

    path(
        "restaurant-admin/customers-status/",
        AdminCustomersStatsView.as_view(),
        name="restaurant-admin-customer-detail",
    ),

    # =============================
    # 🔹 Include Router URLs
    # =============================
    path("", include(router.urls)),
]
