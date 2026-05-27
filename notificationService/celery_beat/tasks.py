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
def delete_read_notifications(self):
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

            # CRITICAL FOR RDS/SUPABASE: Flush Django's connection state cache
            if hasattr(connection, 'close_if_unusable_or_obsolete'):
                connection.close_if_unusable_or_obsolete()

            # Execute delete within the verified schema context boundary
            deleted_count, _ = Notification.objects.filter(is_read=True).delete()
            total_deleted += deleted_count

            if deleted_count > 0:
                logger.warning(f"🗑️ Deleted {deleted_count} read notifications | schema={schema}")
            else:
                logger.info(f"✅ No stale notifications found | schema={schema}")

        except Exception as e:
            logger.exception(f"❌ Failed cleaning notifications | schema={schema}")
            # Individual schema failures won't break the entire worker process loop
            continue

        finally:
            # Revert connection path reference back to safe tracking standards
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public")
            except Exception:
                logger.error(f"🚨 Failed tracking clean context reset step back to public boundary after leaving schema={schema}")

    logger.info(f"🏁 Notification cleanup finished | total_deleted={total_deleted}")
    return total_deleted