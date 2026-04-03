from cart.views import HealthCheckView
from django.urls import path, include
from common.views import TenantProvisionView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


urlpatterns = [
    path("api/cart/", include("cart.urls")),
    path("health/", HealthCheckView.as_view(), name="cart-health"),

    path("internal/tenants/provision", TenantProvisionView.as_view()),

    path("api/cart/schema/", SpectacularAPIView.as_view(authentication_classes=[],
                                                        permission_classes=[],), name="auth-schema"),
    # Swagger UI
    path("api/cart/swagger/",
         SpectacularSwaggerView.as_view(url_name="auth-schema"), name="swagger-ui"),
]
