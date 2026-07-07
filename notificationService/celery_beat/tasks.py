# celery_beat/tasks.py
from celery import shared_task
from django.db import connection
import logging
import os
from firebase_pushnotification.models import Notification

logger = logging.getLogger(__name__)

# Identify this service context explicitly (defaults to 'notification')
SERVICE_NAME = os.getenv("SERVICE_NAME", "notification").lower()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
)
def delete_readed_notifications(self):
    total_deleted = 0
    schemas = []

    try:
        # ----------------------------------
        # Fetch ONLY schemas belonging to THIS service
        # ----------------------------------
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            
            # Using LIKE to filter for matching prefixes (e.g., 'notification_%')
            cursor.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name LIKE %s
                  AND schema_name NOT IN (
                    'public',
                    'information_schema',
                    'pg_catalog',
                    'pg_toast'
                  )
            """, [f"{SERVICE_NAME}_%"])
            
            schemas = [row[0] for row in cursor.fetchall()]

        logger.info(f"🏢 Found {len(schemas)} matching tenant schemas for service '{SERVICE_NAME}'")

    except Exception as e:
        logger.exception("❌ Failed fetching service-specific tenant schemas from public database directory.")
        raise e

    # ----------------------------------
    # Iterate service tenants securely
    # ----------------------------------
    for schema in schemas:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}", public')

                cursor.execute("SHOW search_path")
                logger.info(f"search_path = {cursor.fetchone()[0]}")

                cursor.execute("SELECT current_schema()")
                logger.info(f"current_schema = {cursor.fetchone()[0]}")

                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = current_schema()
                        AND table_name = 'firebase_pushnotification_notification'
                    )
                """)
                logger.info(f"table exists = {cursor.fetchone()[0]}")

            deleted_count, _ = Notification.objects.filter(
                is_read=True
            ).delete()

            total_deleted += deleted_count

            logger.info(
                f"Deleted {deleted_count} notifications from {schema}"
            )

        except Exception:
            logger.exception(
                f"Failed cleaning notifications | schema={schema}"
            )

        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")
                
    logger.info(f"🏁 Notification cleanup finished | total_deleted={total_deleted}")
    return total_deleted