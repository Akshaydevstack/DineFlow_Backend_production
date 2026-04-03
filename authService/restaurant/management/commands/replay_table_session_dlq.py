import json
import logging
import signal

from django.core.management.base import BaseCommand
from confluent_kafka import Consumer
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError

from kafka.table_session_consumer import process_event
from kafka.table_session_dlq_producer import send_to_table_session_dlq

logger = logging.getLogger(__name__)

CONSUMER_NAME = "auth-table-session-dlq-replay"
DLQ_TOPIC = "table.session.dlq"

running = True


# --------------------------------------------------
# Graceful shutdown
# --------------------------------------------------
def shutdown(signum, frame):
    global running
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


class Command(BaseCommand):
    help = "Replay Auth Table Session DLQ events"

    def handle(self, *args, **options):

        self.stdout.write("🔁 Table Session DLQ replay started")

        consumer = Consumer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "group.id": CONSUMER_NAME,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })

        consumer.subscribe([DLQ_TOPIC])

        try:
            while running:

                msg = consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error(msg.error())
                    continue

                try:
                    payload = json.loads(msg.value())

                    original_topic = payload["original_topic"]
                    event = payload["event"]

                    # --------------------------------------
                    # Replay original event
                    # --------------------------------------
                    with transaction.atomic():
                        process_event(event, original_topic)

                    consumer.commit(msg)

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Replayed table session event | table={event.get('table_public_id')}"
                        )
                    )

                # --------------------------------------------------
                # Still failing → Keep in DLQ
                # --------------------------------------------------
                except (KeyError, ValidationError, ValueError) as e:
                    logger.warning(
                        "❌ Table session DLQ replay failed again",
                        extra={
                            "error": str(e),
                            "payload": payload,
                        },
                    )

                    # Optional: re-send with retry_count+1
                    retry_count = payload.get("retry_count", 0) or 0

                    send_to_table_session_dlq(
                        topic=original_topic,
                        event=event,
                        error=e,
                        consumer=CONSUMER_NAME,
                        dlq_topic=DLQ_TOPIC,
                        key=event.get("table_public_id"),
                        retry_count=retry_count + 1,
                    )

                    consumer.commit(msg)

                except Exception:
                    logger.exception(
                        "🔥 Unexpected error during DLQ replay — retrying"
                    )
                    continue

        finally:
            consumer.close()
            self.stdout.write("🛑 Table Session DLQ replay stopped")