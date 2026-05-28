import os
import re
from django.db import connection
from django.http import JsonResponse

TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# Fetching service name from env
SERVICE_NAME = os.getenv("SERVICE_NAME", "cart")


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

        try:
            with connection.cursor() as cursor:
                # Included the underscore delimiter between SERVICE_NAME and schema
                cursor.execute(
                    f'SET search_path TO "{SERVICE_NAME}_{schema}", public'
                )

            return self.get_response(request)

        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")