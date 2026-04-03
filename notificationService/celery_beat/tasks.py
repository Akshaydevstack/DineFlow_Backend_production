# celery_beat/tasks.py
from celery import shared_task
from django.db import connection
import logging
from firebase_pushnotification.models import Notification

logger = logging.getLogger(__name__)


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
        # Fetch all tenant schemas
        # ----------------------------------
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN (
                    'public',
                    'information_schema',
                    'pg_catalog',
                    'pg_toast'
                )
            """)
            schemas = [row[0] for row in cursor.fetchall()]

        # ----------------------------------
        # Iterate tenants
        # ----------------------------------
        for schema in schemas:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f'SET search_path TO "{schema}", public')

                deleted_count, _ = Notification.objects.filter(
                    is_read = True
                ).delete()

                total_deleted += deleted_count

                logger.info(
                    f"🗑️ Deleted {deleted_count} READED notifications | schema={schema}"
                )

            except Exception as e:
                logger.exception(
                    f"❌ Failed cleaning READED notifications | schema={schema}"
                )

    finally:
        # ----------------------------------
        # ALWAYS reset schema (CRITICAL)
        # ----------------------------------
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")

        logger.info(
            f"✅ Notification cleanup finished | total_deleted={total_deleted}"
        )

    return total_deleted