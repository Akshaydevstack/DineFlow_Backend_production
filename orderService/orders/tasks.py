from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone
from datetime import timedelta
import logging

from orders.models import TableSession
from orders.kafka.producer import publish_session_closed

logger = logging.getLogger(__name__)


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

        logger.info(f"🏢 Found {len(schemas)} tenant schemas")

        # ----------------------------------
        # Iterate tenants
        # ----------------------------------
        for schema in schemas:

            try:
                # Switch schema
                with connection.cursor() as cursor:
                    cursor.execute(f'SET search_path TO "{schema}", public')

                idle_sessions = TableSession.objects.filter(
                    status=TableSession.STATUS_ACTIVE,
                    last_activity_at__lt=cutoff,
                )

                count = idle_sessions.count()

                if count == 0:
                    logger.info(f"✅ No idle sessions | schema={schema}")
                    continue

                logger.warning(
                    f"⚠️ Found {count} idle sessions | schema={schema}"
                )

                for session in idle_sessions:

                    with transaction.atomic():

                        session.status = TableSession.STATUS_CLOSED
                        session.closed_at = now
                        session.save(update_fields=["status", "closed_at"])

                        transaction.on_commit(
                            lambda s=session: publish_session_closed(s)
                        )

                        total_closed += 1

                        logger.info(
                            f"🔒 Auto-closed session {session.public_id} | schema={schema}"
                        )

            except Exception:
                logger.exception(
                    f"❌ Failed closing idle sessions | schema={schema}"
                )

    finally:
        # ----------------------------------
        # ALWAYS reset schema (CRITICAL)
        # ----------------------------------
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")

        logger.info(
            f"✅ Idle session cleanup finished | total_closed={total_closed}"
        )

    return total_closed