import os
import re
from django.db import connection

# Matches 'rest_' followed by alphanumeric characters (e.g., 'rest_123')
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

# Pull the microservice identifier from your environment configuration (e.g., 'auth', 'notification', 'order')
SERVICE_NAME = os.getenv("SERVICE_NAME", "notification").lower()


def set_schema(restaurant_id: str):
    """
    Constructs the service-specific tenant schema name and safely binds it 
    to the active Postgres connection context and application metrics.
    """
    if not restaurant_id:
        raise ValueError("Restaurant ID missing")

    base_tenant = restaurant_id.lower().strip()
    if not TENANT_REGEX.match(base_tenant):
        raise ValueError(f"Invalid restaurant id format: {base_tenant}")

    # Construct the identical targeted schema name used by your middleware
    target_schema = f"{SERVICE_NAME}_{base_tenant}"
    
    # Create an identifiable app descriptor string for tracking inside cloud tools/RDS
    application_tracking_tag = f"{SERVICE_NAME}:{base_tenant}"

    with connection.cursor() as cursor:
        # 1. Update the search path routing sequence
        cursor.execute(f'SET search_path TO "{target_schema}", public')
        
        # 2. Update Postgres runtime application_name parameter for performance logging
        cursor.execute(f"SET application_name TO '{application_tracking_tag}'")
        
    # Flush Django's connection layer cache to guarantee it respects the new schema mapping
    if hasattr(connection, 'close_if_unusable_or_obsolete'):
        connection.close_if_unusable_or_obsolete()


def reset_schema():
    """
    Resets the database connection context cleanly back to the shared public space.
    """
    application_tracking_tag = f"{SERVICE_NAME}:public"

    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
        cursor.execute(f"SET application_name TO '{application_tracking_tag}'")