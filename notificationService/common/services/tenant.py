import re
from django.db import connection
from django.core.management import call_command

TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")


def provision_tenant(schema_name: str):
    if not schema_name:
        raise ValueError("tenant_id is required")

    if not TENANT_REGEX.match(schema_name):
        raise ValueError("Invalid tenant_id format")

  
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

    
    with connection.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{schema_name}", public')

  
    call_command("migrate", interactive=False)



def deprovision_tenant(schema_name: str):
    
    if not schema_name:
        raise ValueError("tenant_id is required")

    if not TENANT_REGEX.match(schema_name):
        raise ValueError("Invalid tenant_id format")

    
    if schema_name in ["public", "information_schema", "postgres"]:
        raise ValueError(f"Cannot drop system schema: {schema_name}")

   
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')