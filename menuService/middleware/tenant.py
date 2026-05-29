import os
import re
from django.db import connection
from django.http import JsonResponse

TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")
SERVICE_NAME = os.getenv("SERVICE_NAME", "menu")


class TenantSchemaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.path.startswith((
            "/health",
            "/internal/tenants",
            "/api/order/swagger/",
            "/api/order/schema/"
        )):
            return self.get_response(request)

        tenant_id = request.headers.get("X-Restaurant-Id")

        if not tenant_id:
            return JsonResponse(
                {"error": "X-Restaurant-Id header missing"},
                status=400
            )

        schema = tenant_id.lower()

        if not TENANT_REGEX.match(schema):
            return JsonResponse(
                {"error": "Invalid tenant id"},
                status=400
            )

        # ✅ Set schema directly on the connection before the request
        target_schema = f"{SERVICE_NAME}_{schema}"
        connection.connection  # ensure connection is open
        
        with connection.cursor() as cursor:
            cursor.execute(
                f"SET LOCAL search_path TO \"{target_schema}\", public"  # ✅ SET LOCAL instead of SET
            )

        return self.get_response(request)
        # ✅ No finally reset needed — SET LOCAL auto-resets after transaction ends