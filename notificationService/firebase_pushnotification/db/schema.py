import os
import re
# 🔴 CHANGE THIS: Import 'connections' and 'DEFAULT_DB_ALIAS', NOT 'connection'
from django.db import connections, DEFAULT_DB_ALIAS

TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")
SERVICE_NAME = os.getenv("SERVICE_NAME", "notification").lower()


def set_schema(restaurant_id: str):
    if not restaurant_id:
        raise ValueError("Restaurant ID missing")

    base_tenant = restaurant_id.lower().strip()
    if not TENANT_REGEX.match(base_tenant):
        raise ValueError(f"Invalid restaurant id format: {base_tenant}")

    target_schema = f"{SERVICE_NAME}_{base_tenant}"
    application_tracking_tag = f"{SERVICE_NAME}:{base_tenant}"

    # ✅ Fix 1: Explicitly get the isolated connection pointer for this thread
    conn = connections[DEFAULT_DB_ALIAS]
    
    # ✅ Fix 2: Clear out cached model tables from previous schema contexts immediately
    if hasattr(conn, 'close_if_unusable_or_obsolete'):
        conn.close_if_unusable_or_obsolete()

    with conn.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{target_schema}", public')
        cursor.execute(f"SET application_name TO '{application_tracking_tag}'")


def reset_schema():
    application_tracking_tag = f"{SERVICE_NAME}:public"
    
    # ✅ Fix 3: Clean up the isolated connection pointer on exit
    conn = connections[DEFAULT_DB_ALIAS]

    with conn.cursor() as cursor:
        cursor.execute("SET search_path TO public")
        cursor.execute(f"SET application_name TO '{application_tracking_tag}'")