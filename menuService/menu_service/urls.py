from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import AllowAny
from dishes.views import HealthCheckView
from dishes.internal_views import InternalDishDetailView,InternalDishBatchView
from common.views import TenantProvisionView

urlpatterns = [
    # ================= API =================
    path("api/menu/", include("dishes.urls")),
    path("api/menu/", include("dish_reviews.urls")),
    path("api/menu/", include("categories.urls")),

     # ================= internal for Dish validations & dishdetaisl =================
    path("internal/dishes/batch/",InternalDishBatchView.as_view(),name="internal-dish-batch"),
    path("internal/dishes/<str:public_id>/",InternalDishDetailView.as_view(),name="internal-dish-detail"),
   

    # ================= HEALTH =================
    path("health/", HealthCheckView.as_view(), name="menu-health"),

    # ================= internal for shema =================

    path("internal/tenants/provision", TenantProvisionView.as_view()),

    # ================= SCHEMA =================
   path(
        "api/menu/schema/",
        SpectacularAPIView.as_view(
            authentication_classes=[],
            permission_classes=[],
        ),
        name="menu-schema",   
    ),

    # 🔹 Swagger UI
    path(
        "api/menu/swagger/",
        SpectacularSwaggerView.as_view(
            url_name="menu-schema" 
        ),
        name="menu-swagger",
    ),
]