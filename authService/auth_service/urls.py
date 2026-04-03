from django.contrib import admin
from django.urls import path, include


from accounts.views import HealthCheckView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # ================= HEALTH =================
    path("health/", HealthCheckView.as_view(), name="auth-health"),

    # ================= AUTH API =================
    path("api/auth/", include("accounts.urls")),

    # ================= SUPERADMIN API =================

    path("api/auth/", include("restaurant.urls")),

    # ================= SWAGGER =================
    # Schema
    path("api/auth/schema/", SpectacularAPIView.as_view(authentication_classes=[],
                                                        permission_classes=[],), name="auth-schema"),
    # Swagger UI
    path("api/auth/swagger/",
         SpectacularSwaggerView.as_view(url_name="auth-schema"), name="swagger-ui"),
]
