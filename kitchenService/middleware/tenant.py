import re
from django.db import connection
from django.http import JsonResponse

TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")

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

        schema_name = tenant_id.lower()

        if not TENANT_REGEX.match(schema_name):
            return JsonResponse(
                {"error": "Invalid tenant schema"},
                status=400,
            )

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SET search_path TO "{schema_name}", public'
                )

            response = self.get_response(request)
            return response

        finally:
            with connection.cursor() as cursor:
                cursor.execute('SET search_path TO public')