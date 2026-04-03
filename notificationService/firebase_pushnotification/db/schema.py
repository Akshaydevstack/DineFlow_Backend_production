import re
from django.db import connection

TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")


def set_schema(schema: str):
    if not schema:
        raise ValueError("schema missing")

    schema = schema.lower()
    if not TENANT_REGEX.match(schema):
        raise ValueError(f"Invalid schema: {schema}")

    with connection.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{schema}", public')


def reset_schema():
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")