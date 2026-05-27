import os
import re
from django.db import connection, transaction
from django.http import JsonResponse

# 🟢 FIX 1: Standardized regex to match your other services and provisioning script
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# 🟢 FIX 2: Pull the service name from env (Defaults to 'kitchen')
SERVICE_NAME = os.getenv("SERVICE_NAME", "kitchen")

class TenantSchemaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith((
            "/health",
            "/internal",
            "/api/kitchen/schema/",
            "/api/kitchen/swagger/"
        )):
            return self.get_response(request)

        tenant_id = request.headers.get("X-Restaurant-Id")

        if not tenant_id:
            return JsonResponse(
                {"error": "X-Restaurant-Id header missing"},
                status=400,
            )

        base_tenant = tenant_id.lower()

        if not TENANT_REGEX.match(base_tenant):
            return JsonResponse(
                {"error": "Invalid tenant schema"},
                status=400,
            )

        # 🟢 FIX 3: Construct the isolated schema name (e.g., 'kitchen_rest_123')
        target_schema = f"{SERVICE_NAME}_{base_tenant}"

        try:
            # 🟢 FIX 4: Wrap in an atomic block and use SET LOCAL for Supabase pooler safety
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Validated via regex, so f-string injection is completely safe here
                    cursor.execute(f'SET LOCAL search_path TO "{target_schema}", public')

                # The view executes safely inside this isolated transaction block
                return self.get_response(request)
        except Exception as e:
            # Re-raise the exception after the transaction rolls back
            raise e