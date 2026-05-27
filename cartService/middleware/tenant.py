import os
import re
from django.db import connection, transaction
from django.http import JsonResponse

TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# 🟢 FIX 1: Grab the service name from env (Defaults to 'cart')
SERVICE_NAME = os.getenv("SERVICE_NAME", "cart")

class TenantSchemaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Skip paths that don't need tenant isolation
        if request.path.startswith((
            "/health",
            "/internal/tenants/",
            "/api/cart/schema/",
            "/api/cart/swagger/"
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
            
        # 🟢 FIX 1: Construct the isolated schema name (e.g., 'cart_rest_a')
        target_schema = f"{SERVICE_NAME}_{base_tenant}"
        
        try:
            # 🟢 FIX 2: Wrap in an atomic block and use SET LOCAL for Supabase safety
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'SET LOCAL search_path TO "{target_schema}", public')
                
                # The view executes safely inside this isolated transaction block
                return self.get_response(request)
        except Exception as e:
            # Re-raise the exception after the transaction rolls back
            raise e