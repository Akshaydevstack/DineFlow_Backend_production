from celery import shared_task
from django.db import connections, DEFAULT_DB_ALIAS, transaction
from django.utils import timezone
from datetime import timedelta
import logging
import os

from orders.models import TableSession
from orders.kafka.producer import publish_session_closed

logger = logging.getLogger(__name__)

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

    # ✅ Force isolated connection lookup context
    conn = connections[DEFAULT_DB_ALIAS]

    try:
        # Clear any stale connection state before starting
        if hasattr(conn, 'close_if_unusable_or_obsolete'):
            conn.close_if_unusable_or_obsolete()

        with conn.cursor() as cursor:
            cursor.execute("SET search_path TO public")
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
            # ✅ Explicitly ensure the connection is fresh for this loop cycle
            if hasattr(conn, 'close_if_unusable_or_obsolete'):
                conn.close_if_unusable_or_obsolete()

            with conn.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}", public')

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
            # Revert cleanly using the isolated connection object
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SET search_path TO public")
            except Exception:
                logger.error(f"🚨 Failed tracking safe schema fallback step back to public boundary from schema={schema}")

    logger.info(f"✅ Idle session cleanup finished | total_closed={total_closed}")
    return total_closed