from django.urls import path,include
from tickets.views import HealthCheckView
from common.views import TenantProvisionView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
urlpatterns = [
   path("health/", HealthCheckView.as_view()),
   path("api/kitchen/", include("tickets.urls")),
   path("internal/tenants/provision", TenantProvisionView.as_view()),
    path("api/kitchen/schema/", SpectacularAPIView.as_view(authentication_classes=[],
                                                        permission_classes=[],), name="auth-schema"),
    # Swagger UI
    path("api/kitchen/swagger/",
         SpectacularSwaggerView.as_view(url_name="auth-schema"), name="swagger-ui"),
]
