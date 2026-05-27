import os
import json
import logging
import re
import signal
from decimal import Decimal

from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from django.core.exceptions import ValidationError

from cart.models import MenuItemSnapshot
from cart.kafka.dlq_producer import send_to_dlq

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Config
# --------------------------------------------------
CONSUMER_NAME = "cart-menu-consumer"
DLQ_TOPIC = "cart.menu.dlq"

# 🟢 FIX 1: Pull the service name to prevent schema collisions
SERVICE_NAME = os.getenv("SERVICE_NAME", "cart")

# Standardized regex to match your other services
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")

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
    "enable.auto.commit": False,
})

consumer.subscribe(list(VALID_TOPICS))


# --------------------------------------------------
# Event processor
# --------------------------------------------------

def process_event(event: dict, topic: str):
    if topic not in VALID_TOPICS:
        raise ValueError(f"Unknown topic: {topic}")

    restaurant_id = event.get("restaurant_id")
    dish_id = event.get("dish_id")

    if not restaurant_id or not dish_id:
        raise ValueError(f"Invalid payload: {event}")

    incoming_version = int(event["menu_version"].lstrip("v"))

    # 🟢 FIX 2: Construct target schema and validate
    base_tenant = restaurant_id.lower()
    if not TENANT_REGEX.match(base_tenant):
        raise ValueError(f"Invalid schema: {base_tenant}")
        
    target_schema = f"{SERVICE_NAME}_{base_tenant}"

    # 🟢 FIX 3: Atomic Transaction + SET LOCAL for Pooler Safety
    # We removed the separate _set_schema() and _reset_schema() functions.
    # Everything happens inside this atomic block so the connection is locked.
    with transaction.atomic():
        with connection.cursor() as cursor:
            # SET LOCAL guarantees this search path only exists for this specific transaction
            cursor.execute(f'SET LOCAL search_path TO "{target_schema}", public')

        existing = MenuItemSnapshot.objects.filter(
            restaurant_id=restaurant_id,
            dish_id=dish_id,
        ).first()

        # --------------------------------------------------
        # VERSION GUARD (CRITICAL)
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
                    "original_price": event["original_price"]
                },
            )

            logger.info(
                f"🧾 Cart menu snapshot upserted | "
                f"dish={dish_id} | restaurant={restaurant_id} | "
                f"incoming_v=v{incoming_version} "
            )

        # --------------------------------------------------
        # DELETE → soft delete
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
                "🛒 Cart menu snapshot marked unavailable",
                extra={
                    "restaurant_id": restaurant_id,
                    "dish_id": dish_id,
                },
            )
            
    # When the 'with transaction.atomic()' block ends, PostgreSQL automatically 
    # clears the LOCAL search_path. No manual reset is needed!


# --------------------------------------------------
# Main consumer loop
# --------------------------------------------------

def consume_menu_events():
    logger.info("🛒 Cart Menu Snapshot Kafka consumer started")

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

                # Commit ONLY after successful processing and database commit
                consumer.commit(msg)

            # --------------------------------------------------
            # ❌ Non-retriable → DLQ
            # --------------------------------------------------
            except (KeyError, ValidationError, ValueError) as e:
                logger.warning(
                    "❌ Non-retriable cart menu event",
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

                consumer.commit(msg)  

            # --------------------------------------------------
            # 🔁 Retriable → Kafka offset retry
            # --------------------------------------------------
            except Exception:
                logger.exception(
                    "🔥 Cart menu consumer failed — retrying via Kafka offset"
                )
                # ❌ DO NOT COMMIT
                continue

    finally:
        logger.info("🛑 Cart menu consumer shutting down")
        consumer.close()