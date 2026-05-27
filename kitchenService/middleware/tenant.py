import os
import re
from django.db import connection
from django.http import JsonResponse

# Matches 'rest_' followed by alphanumeric characters (e.g., 'rest_298bf97a')
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# Pull the microservice identifier from env (e.g., 'order', 'notification', 'auth')
SERVICE_NAME = os.getenv("SERVICE_NAME", "kitchen").lower()


class TenantSchemaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Skip paths that don't require isolated tenant database routing
        if request.path.startswith((
            "/health",
            "/internal/tenants",
            "/api/order/swagger/",
            "/api/order/schema/"
        )):
            return self.get_response(request)

        # 2. Extract and sanitize the tracking context restaurant header
        tenant_id = request.headers.get("X-Restaurant-Id")

        if not tenant_id:
            return JsonResponse(
                {"error": "X-Restaurant-Id header missing"},
                status=400
            )

        base_tenant = tenant_id.lower().strip()

        if not TENANT_REGEX.match(base_tenant):
            return JsonResponse(
                {"error": "Invalid tenant id format"},
                status=400
            )

        # 3. Construct the matching target isolated schema (e.g., 'order_rest_298bf97a')
        target_schema = f"{SERVICE_NAME}_{base_tenant}"

        try:
            # Point the active connection path to the current tenant's tablespace
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{target_schema}", public')

            # CRITICAL FOR MULTI-TENANCY WORKING RELIABLY: 
            # Flush Django's routing wrapper cache so the ORM respects the path switch immediately
            if hasattr(connection, 'close_if_unusable_or_obsolete'):
                connection.close_if_unusable_or_obsolete()

            # Pass request execution down into the target API view layer safely
            return self.get_response(request)

        finally:
            # 4. ALWAYS cleanly reset search path back to public to prevent connection bleeding
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public")
            except Exception:
                pass