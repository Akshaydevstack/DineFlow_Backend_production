from django.urls import path,include
from common.views import TenantProvisionView
from orders.views import HealthCheckView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("api/order/", include("orders.urls")),
    path("health/", HealthCheckView.as_view()),
    path("internal/tenants/provision", TenantProvisionView.as_view()),

    path(
        "api/order/schema/",
        SpectacularAPIView.as_view(
            authentication_classes=[],
            permission_classes=[],
        ),
        name="menu-schema",   
    ),

    # 🔹 Swagger UI
    path(
        "api/order/swagger/",
        SpectacularSwaggerView.as_view(
            url_name="menu-schema" 
        ),
        name="menu-swagger",
    )
]
