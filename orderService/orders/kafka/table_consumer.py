import json
import logging
import re
import signal

from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from django.core.exceptions import ValidationError

from orders.models import TableSnapshot
from orders.kafka.dlq_producer import send_to_dlq

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Config
# --------------------------------------------------
CONSUMER_NAME = "order-table-consumer"
DLQ_TOPIC = "order.table.dlq"
TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")

VALID_TOPIC = "restaurant.table.upsert"

running = True


# --------------------------------------------------
# Graceful shutdown
# --------------------------------------------------
def shutdown(signum, frame):
    global running
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# --------------------------------------------------
# Kafka Consumer
# --------------------------------------------------
consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKER,
    "group.id": CONSUMER_NAME,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

consumer.subscribe([VALID_TOPIC])


# --------------------------------------------------
# Tenant schema helpers
# --------------------------------------------------
def _set_schema(restaurant_id: str):
    if not restaurant_id:
        raise ValueError("restaurant_id missing")

    schema = restaurant_id.lower()

    if not TENANT_REGEX.match(schema):
        raise ValueError(f"Invalid schema: {schema}")

    with connection.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{schema}", public')


def _reset_schema():
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")


# --------------------------------------------------
# Event processor (IDEMPOTENT + VERSIONED)
# --------------------------------------------------
def process_event(event: dict):
    if event.get("event_type") != "TABLE_UPSERT":
        raise ValueError("Invalid event_type")

    restaurant_id = event.get("restaurant_id")
    table_id = event.get("table_public_id")

    if not restaurant_id or not table_id:
        raise ValueError(f"Invalid payload: {event}")

    incoming_version = int(event["version"].lstrip("v"))

    _set_schema(restaurant_id)

    try:
        with transaction.atomic():

            existing = TableSnapshot.objects.filter(
                restaurant_id=restaurant_id,
                table_public_id=table_id,
            ).first()

            # --------------------------------------------------
            # VERSION GUARD
            # --------------------------------------------------
            if existing:
                current_version = int(existing.table_version.lstrip("v"))

                if incoming_version <= current_version:
                    logger.info(
                        "⏭️ Skipping stale table event",
                        extra={
                            "table_id": table_id,
                            "incoming_version": incoming_version,
                            "current_version": current_version,
                        },
                    )
                    return

            # --------------------------------------------------
            # UPSERT SNAPSHOT
            # --------------------------------------------------
            TableSnapshot.objects.update_or_create(
                restaurant_id=restaurant_id,
                table_public_id=table_id,
                defaults={
                    "restaurant_name": event["restaurant_name"],
                    "table_number": event["table_number"],
                    "zone_public_id": event.get("zone_public_id"),
                    "zone_name": event.get("zone_name"),
                    "is_active": event["is_active"],
                    "table_version": event["version"],
                },
            )

            logger.info(
                f"🪑 Table snapshot upserted | table={table_id} | restaurant={restaurant_id} | v{incoming_version}"
            )

    finally:
        _reset_schema()


# --------------------------------------------------
# Main consumer loop
# --------------------------------------------------
def consume_table_events():
    logger.info("🪑 Order Table Snapshot Kafka consumer started")

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(msg.error())
                continue

            try:
                event = json.loads(msg.value())

                process_event(event)

                # ✅ Commit only after success
                consumer.commit(msg)

            # --------------------------------------------------
            # Non-retriable → DLQ
            # --------------------------------------------------
            except (KeyError, ValidationError, ValueError) as e:
                logger.warning(
                    "❌ Non-retriable table event",
                    extra={
                        "error": str(e),
                        "payload": msg.value(),
                    },
                )

                send_to_dlq(
                    topic=VALID_TOPIC,
                    event=event,
                    error=e,
                    consumer=CONSUMER_NAME,
                    dlq_topic=DLQ_TOPIC,
                    key=event.get("table_public_id"),
                )

                consumer.commit(msg)

            # --------------------------------------------------
            # Retriable → Kafka retry (offset-based)
            # --------------------------------------------------
            except Exception:
                logger.exception(
                    "🔥 Order table consumer failed — retrying via Kafka offset"
                )
                # DO NOT COMMIT
                continue

    finally:
        logger.info("🛑 Order table consumer shutting down")
        consumer.close()