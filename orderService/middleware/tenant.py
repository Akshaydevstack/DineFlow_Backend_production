import os
import re
from django.db import connection, transaction
from django.http import JsonResponse

# 🟢 FIX 1: Standardized regex 
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# 🟢 FIX 2: Pull the service name from env (Defaults to 'order')
SERVICE_NAME = os.getenv("SERVICE_NAME", "order")

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

        base_tenant = tenant_id.lower()

        if not TENANT_REGEX.match(base_tenant):
            return JsonResponse(
                {"error": "Invalid tenant id"},
                status=400
            )

        # 🟢 FIX 3: Construct the isolated schema name (e.g., 'order_rest_123')
        target_schema = f"{SERVICE_NAME}_{base_tenant}"

        try:
            # 🟢 FIX 4: Wrap in an atomic block and use SET LOCAL for Supabase pooler safety
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Safely inject the validated schema name
                    cursor.execute(f'SET LOCAL search_path TO "{target_schema}", public')

                # The view executes safely inside this isolated transaction block
                return self.get_response(request)
        except Exception as e:
            # Re-raise the exception after the transaction rolls back
            raise e