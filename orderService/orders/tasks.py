from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone
from datetime import timedelta
import logging
import os

from orders.models import TableSession
from orders.kafka.producer import publish_session_closed

logger = logging.getLogger(__name__)

# Identify this service context explicitly (defaults to 'order' for this task)
SERVICE_NAME = os.getenv("SERVICE_NAME", "order").lower()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
)
def close_idle_sessions(self):
    TIMEOUT_MINUTES = 30
    now = timezone.now()
    cutoff = now - timedelta(minutes=TIMEOUT_MINUTES)

    total_closed = 0
    schemas = []

    try:
        # ----------------------------------
        # Fetch ONLY schemas belonging to THIS service
        # ----------------------------------
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            
            # Added a WHERE clause filter to isolate prefix paths (e.g., 'order_%')
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

            # CRITICAL: Flush connection layer state cache to force Django to bind to the new search path completely
            if hasattr(connection, 'close_if_unusable_or_obsolete'):
                connection.close_if_unusable_or_obsolete()

            # Execute lookup within the target tenant boundary safely
            idle_sessions = list(
                TableSession.objects.filter(
                    status=TableSession.STATUS_ACTIVE,
                    last_activity_at__lt=cutoff,
                )
            )

            count = len(idle_sessions)

            if count == 0:
                logger.info(f"✅ No idle sessions | schema={schema}")
                continue

            logger.warning(f"⚠️ Found {count} idle sessions | schema={schema}")

            for session in idle_sessions:
                try:
                    with transaction.atomic():
                        session.status = TableSession.STATUS_CLOSED
                        session.closed_at = now
                        session.save(update_fields=["status", "closed_at"])

                        # Pin current instance scope context closure variables securely for Kafka dispatches
                        transaction.on_commit(
                            lambda s=session: publish_session_closed(s)
                        )

                        total_closed += 1
                        logger.info(f"🔒 Auto-closed session {session.public_id} | schema={schema}")
                except Exception:
                    logger.exception(f"❌ Failed processing atomic row close for session {session.id} | schema={schema}")
                    continue

        except Exception:
            logger.exception(f"❌ Critical failure running sequence execution loop | schema={schema}")
        finally:
            # Revert connection references at the close of every evaluation cycle step
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public")
            except Exception:
                logger.error(f"🚨 Failed tracking safe schema fallback step back to public boundary from schema={schema}")

    logger.info(f"✅ Idle session cleanup finished | total_closed={total_closed}")
    return total_closed