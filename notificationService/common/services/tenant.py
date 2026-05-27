import os
import re
from django.db import connection
from django.core.management import call_command

# 🟢 FIX 1: Standardized regex to match the middleware
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# 🟢 FIX 2: Dynamically pull the service name
SERVICE_NAME = os.getenv("SERVICE_NAME", "default_service")

def provision_tenant(tenant_id: str):
    if not tenant_id:
        raise ValueError("tenant_id is required")

    tenant_id = tenant_id.lower()
    if not TENANT_REGEX.match(tenant_id):
        raise ValueError("Invalid tenant_id format")

    # Construct the target schema (e.g., 'notification_rest_123')
    target_schema = f"{SERVICE_NAME}_{tenant_id}"

    try:
        with connection.cursor() as cursor:
            # Create the schema specific to this microservice
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"')
            
            # Lock this specific connection to the new schema
            cursor.execute(f'SET search_path TO "{target_schema}", public')

        # Run Django migrations. Because the connection's search_path is set, 
        # Django will build the tables strictly inside target_schema.
        call_command("migrate", interactive=False)
        
    finally:
        # 🟢 FIX 3: SUPABASE POOLER SAFETY NET
        # Reset the search path back to public after migrating.
        with connection.cursor() as cursor:
            cursor.execute('SET search_path TO public')


def deprovision_tenant(tenant_id: str):
    if not tenant_id:
        raise ValueError("tenant_id is required")

    tenant_id = tenant_id.lower()
    if not TENANT_REGEX.match(tenant_id):
        raise ValueError("Invalid tenant_id format")

    # Construct the target schema
    target_schema = f"{SERVICE_NAME}_{tenant_id}"

    # Safety check to prevent accidental deletion of core databases
    protected_schemas = ["public", "information_schema", "postgres", "ai_service", "auth_service"]
    if target_schema in protected_schemas:
        raise ValueError(f"Cannot drop system or core schema: {target_schema}")

    with connection.cursor() as cursor:
        # CASCADE ensures all tables inside the schema are also deleted
        cursor.execute(f'DROP SCHEMA IF EXISTS "{target_schema}" CASCADE')