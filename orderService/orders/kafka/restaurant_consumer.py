import os
import json
import logging
import re
import signal
from dateutil import parser
from contextlib import contextmanager

from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from django.core.exceptions import ValidationError

from orders.models import Restaurant
from orders.kafka.dlq_producer import send_to_dlq

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Config
# --------------------------------------------------
CONSUMER_NAME = "order-restaurant-consumer"
DLQ_TOPIC = "order.restaurant.dlq"

VALID_TOPICS = ["restaurant.created", "restaurant.updated"]

# 🟢 FIX 1: Standardized regex and dynamic service name
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")
SERVICE_NAME = os.getenv("SERVICE_NAME", "order")

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

consumer.subscribe(VALID_TOPICS)


# --------------------------------------------------
# Tenant schema helper (Supabase Pooler Safe)
# --------------------------------------------------
# 🟢 FIX 2: Replaced manual set/reset with the Context Manager
@contextmanager
def tenant_schema(restaurant_id: str):
    if not restaurant_id:
        raise ValueError("restaurant_id missing")

    base_tenant = restaurant_id.lower()
    if not TENANT_REGEX.match(base_tenant):
        raise ValueError(f"Invalid schema: {base_tenant}")

    target_schema = f"{SERVICE_NAME}_{base_tenant}"

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f'SET LOCAL search_path TO "{target_schema}", public')
        yield


# --------------------------------------------------
# Event processor (IDEMPOTENT UPSERT)
# --------------------------------------------------
def process_event(event: dict):
    restaurant_id = event.get("public_id")
    if not restaurant_id:
        raise ValueError(f"Invalid payload: Missing public_id. Payload: {event}")

    # Parse the timestamp
    updated_at_parsed = parser.parse(event["updated_at"])

    # 🟢 FIX 3: Apply the context manager to safely lock the schema
    with tenant_schema(restaurant_id):
        with transaction.atomic():
            
            # --------------------------------------------------
            # UPSERT RESTAURANT REPLICA
            # --------------------------------------------------
            Restaurant.objects.update_or_create(
                public_id=restaurant_id,
                defaults={
                    "name": event.get("name"),
                    "slug": event.get("slug"),
                    "address": event.get("address"),
                    "city": event.get("city"),
                    "state": event.get("state"),
                    "pincode": event.get("pincode"),
                    "latitude": event.get("latitude"),
                    "longitude": event.get("longitude"),
                    "phone": event.get("phone"),
                    "email": event.get("email"),
                    "is_open": event.get("is_open", True),
                    "is_active": event.get("is_active", True),
                    "opening_time": event.get("opening_time"),
                    "closing_time": event.get("closing_time"),
                    "restaurant_version": event.get("restaurant_version", "v1"),
                    "updated_at": updated_at_parsed,
                },
            )

            logger.info(
                f"🏪 Restaurant replica upserted | restaurant={restaurant_id}"
            )


# --------------------------------------------------
# Main consumer loop
# --------------------------------------------------
def consume_restaurant_events():
    logger.info(f"🏪 Order Restaurant Replica Kafka consumer started. Listening to: {VALID_TOPICS}")

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(msg.error())
                continue

            try:
                current_topic = msg.topic()
                event = json.loads(msg.value())

                process_event(event)

                consumer.commit(msg)

            # --------------------------------------------------
            # Non-retriable → DLQ
            # --------------------------------------------------
            except (KeyError, ValidationError, ValueError) as e:
                logger.warning(
                    f"❌ Non-retriable restaurant event on topic {current_topic}",
                    extra={
                        "error": str(e),
                        "payload": msg.value(),
                    },
                )

                send_to_dlq(
                    topic=current_topic,
                    event=event,
                    error=e,
                    consumer=CONSUMER_NAME,
                    dlq_topic=DLQ_TOPIC,
                    key=event.get("public_id"),
                )

                consumer.commit(msg)

            # --------------------------------------------------
            # Retriable → Kafka retry (offset-based)
            # --------------------------------------------------
            except Exception:
                logger.exception(
                    "🔥 Order restaurant consumer failed — retrying via Kafka offset"
                )
                # DO NOT COMMIT so Kafka will deliver it again
                continue

    finally:
        logger.info("🛑 Order restaurant consumer shutting down")
        consumer.close()

if __name__ == "__main__":
    consume_restaurant_events()