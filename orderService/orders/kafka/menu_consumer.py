import json
import logging
import re
import signal
from decimal import Decimal

from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from django.core.exceptions import ValidationError

from orders.models import MenuItemSnapshot
from orders.kafka.dlq_producer import send_to_dlq

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Config
# --------------------------------------------------
CONSUMER_NAME = "order-menu-consumer"
DLQ_TOPIC = "order.menu.dlq"
TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")

VALID_TOPICS = {
    "menu.item.created",
    "menu.item.updated",
    "menu.item.deleted",
}

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
    "enable.auto.commit": False,  # MANUAL COMMIT ONLY
})

consumer.subscribe(list(VALID_TOPICS))

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

def process_event(event: dict, topic: str):
    if topic not in VALID_TOPICS:
        raise ValueError(f"Unknown topic: {topic}")

    restaurant_id = event.get("restaurant_id")
    dish_id = event.get("dish_id")

    if not restaurant_id or not dish_id:
        raise ValueError(f"Invalid payload: {event}")

    incoming_version = int(event["menu_version"].lstrip("v"))

    _set_schema(restaurant_id)

    try:
        with transaction.atomic():

            existing = MenuItemSnapshot.objects.filter(
                restaurant_id=restaurant_id,
                dish_id=dish_id,
            ).first()

            
            # --------------------------------------------------
            # ✅ VERSION GUARD (CRITICAL)
            # --------------------------------------------------

            if existing:
                current_version = int(existing.menu_version.lstrip("v"))
                
                is_stale = False

                if topic == "menu.item.deleted":
                    if incoming_version < current_version:
                        is_stale = True
                else:
                    if incoming_version <= current_version:
                        is_stale = True

                if is_stale:
                    logger.info(
                        "⏭️ Skipping stale cart menu event",
                        extra={
                            "dish_id": dish_id,
                            "topic": topic,
                            "incoming_version": incoming_version,
                            "current_version": current_version,
                        },
                    )
                    return

            # --------------------------------------------------
            # CREATE / UPDATE
            # --------------------------------------------------
            if topic in ("menu.item.created", "menu.item.updated"):
                MenuItemSnapshot.objects.update_or_create(
                    restaurant_id=restaurant_id,
                    dish_id=dish_id,
                    defaults={
                        "name": event["name"],
                        "price": Decimal(event["price"]),
                        "is_available": event["is_available"],
                        "category_id": event.get("category_id"),
                        "image_url": event.get("image_url"),
                        "menu_version": event["menu_version"],
                    },
                )

                logger.info(
                    f"📦 Order menu snapshot upserted | dish={dish_id} | restaurant={restaurant_id}| incomeing_v = v{incoming_version}",
                    extra={
                        "restaurant_id": restaurant_id,
                        "dish_id": dish_id,
                        "menu_version": event["menu_version"],
                    },
                )

            # --------------------------------------------------
            # DELETE → soft delete only
            # --------------------------------------------------
            elif topic == "menu.item.deleted":
                MenuItemSnapshot.objects.filter(
                    restaurant_id=restaurant_id,
                    dish_id=dish_id,
                ).update(
                    is_available=False,
                    menu_version=event["menu_version"],
                )

                logger.info(
                    f"🗑️ Order menu snapshot marked unavailable dish={dish_id}",
                    extra={
                        "restaurant_id": restaurant_id,
                        "dish_id": dish_id,
                    },
                )

    finally:
        _reset_schema()

# --------------------------------------------------
# Main consumer loop
# --------------------------------------------------
def consume_menu_events():
    logger.info("📦 Order Menu Snapshot Kafka consumer started")

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
                topic = msg.topic()

                process_event(event, topic)

                # ✅ Commit ONLY after success
                consumer.commit(msg)

            # --------------------------------------------------
            # ❌ Non-retriable → DLQ
            # --------------------------------------------------
            except (KeyError, ValidationError, ValueError) as e:
                logger.warning(
                    "❌ Non-retriable order-menu event",
                    extra={
                        "error": str(e),
                        "topic": msg.topic(),
                        "payload": msg.value(),
                    },
                )

                send_to_dlq(
                    topic=msg.topic(),
                    event=event,
                    error=e,
                    consumer=CONSUMER_NAME,
                    dlq_topic=DLQ_TOPIC,
                    key=event.get("dish_id"),
                )

                # Commit so Kafka does not retry
                consumer.commit(msg)

            # --------------------------------------------------
            # 🔁 Retriable → Kafka offset retry (NO re-produce)
            # --------------------------------------------------
            except Exception:
                logger.exception(
                    "🔥 Order menu consumer failed — retrying via Kafka offset"
                )
                # ❌ DO NOT COMMIT
                continue

    finally:
        logger.info("🛑 Order menu consumer shutting down")
        consumer.close()