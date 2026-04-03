from django.urls import path,include
from firebase_pushnotification.views import HealthCheckView
from common.views import TenantProvisionView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('api/notification/',include('firebase_pushnotification.urls'),name="firebase-pushnotification"),
    path('health/', HealthCheckView.as_view(),name="helth-check"),
    path("internal/tenants/provision", TenantProvisionView.as_view()),
    path(
        "api/notification/schema/",
        SpectacularAPIView.as_view(
            authentication_classes=[],
            permission_classes=[],
        ),
        name="menu-schema",   
    ),

    # 🔹 Swagger UI
    path(
        "api/notification/swagger/",
        SpectacularSwaggerView.as_view(
            url_name="menu-schema" 
        ),
        name="menu-swagger",
    )
]
