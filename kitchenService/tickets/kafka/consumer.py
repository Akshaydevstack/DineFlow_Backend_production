import os
import json
import logging
import re
import signal
from contextlib import contextmanager

from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from tickets.kafka.ticket_producer import publish_kitchen_ticket_event

from tickets.kafka.handlers import (
    handle_order_placed,
    handle_order_cancelled,
)
from tickets.kafka.producer import get_producer
from tickets.kafka.dlq_producer import send_to_dlq

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Config
# --------------------------------------------------
MAX_RETRIES = 3

# 🟢 FIX 1: Standardized regex and dynamic service name
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")
SERVICE_NAME = os.getenv("SERVICE_NAME", "kitchen")

CONSUMER_NAME = "kitchen-order-consumer"
DLQ_TOPIC = "kitchen.order.dlq"

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

consumer.subscribe([
    "orders.placed",
    "orders.cancelled",
])


# --------------------------------------------------
# Tenant schema helper (Supabase Pooler Safe)
# --------------------------------------------------

# 🟢 FIX 2: Replaced manual set/reset with a robust Context Manager
@contextmanager
def tenant_schema(restaurant_id: str):
    """
    Safely switches to a tenant's schema using a transaction-bound SET LOCAL.
    Automatically reverts to the public schema when the block exits.
    """
    if not restaurant_id:
        raise ValueError("restaurant_id missing")

    base_tenant = restaurant_id.lower()
    if not TENANT_REGEX.match(base_tenant):
        raise ValueError(f"Invalid schema: {base_tenant}")

    # Construct the prefixed schema (e.g., 'kitchen_rest_123')
    target_schema = f"{SERVICE_NAME}_{base_tenant}"

    # Wrap the entire execution in an atomic transaction
    with transaction.atomic():
        with connection.cursor() as cursor:
            # SET LOCAL guarantees this search path ONLY exists for this transaction
            cursor.execute(f'SET LOCAL search_path TO "{target_schema}", public')
        
        yield


# --------------------------------------------------
# Event processor
# --------------------------------------------------
def process_event(event: dict, topic: str):
    restaurant_id = event.get("restaurant_id")
    if not restaurant_id:
        raise ValueError("restaurant_id missing in event")

    # 🟢 FIX 3: Apply the context manager
    with tenant_schema(restaurant_id):
        
        try:
            if topic == "orders.placed":
                # The tenant_schema block is already atomic, but nesting this is 
                # perfectly safe in Django and acts as a savepoint.
                with transaction.atomic():
                    ticket = handle_order_placed(event, restaurant_id)

                    if ticket:
                        transaction.on_commit(
                            lambda: publish_kitchen_ticket_event("CREATED", ticket)
                        )
                        
            elif topic == "orders.cancelled":
                with transaction.atomic():
                    ticket = handle_order_cancelled(event)
                    
                    if ticket:
                        transaction.on_commit(
                            lambda: publish_kitchen_ticket_event("CANCELLED", ticket)
                        )

            else:
                raise ValueError(f"Unknown topic: {topic}")

        except Exception as e:
            # If an error happens, we re-raise it so the retry logic catches it.
            # The context manager will still safely close the database connection.
            raise e


# --------------------------------------------------
# Main consumer loop
# --------------------------------------------------
def consume_order_events():
    logger.info("🍳 Kitchen Order Kafka consumer started")

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(msg.error())
                continue

            headers = dict(msg.headers() or {})
            retry_count = int(
                (headers.get("retry_count") or b"0").decode()
            )

            try:
                event = json.loads(msg.value())
                topic = msg.topic()

                process_event(event, topic)
                consumer.commit(msg)

            # -------------------------
            # Retriable / DLQ logic
            # -------------------------
            except Exception as e:
                if retry_count < MAX_RETRIES:
                    logger.warning(
                        f"🔁 Retrying kitchen event "
                        f"{topic} ({retry_count + 1}/{MAX_RETRIES})"
                    )

                    producer = get_producer()
                    producer.produce(
                        topic=topic,
                        key=msg.key(),
                        value=msg.value(),
                        headers={
                            "retry_count": str(retry_count + 1),
                        },
                    )
                    producer.poll(0)

                else:
                    logger.error("☠️ Kitchen event retries exhausted → DLQ")

                    send_to_dlq(
                        topic=topic,
                        event=event,
                        error=e,
                        consumer=CONSUMER_NAME,
                        dlq_topic=DLQ_TOPIC,
                        key=event.get("order_id"),
                        retry_count=retry_count,
                    )

                consumer.commit(msg)

    finally:
        logger.info("🛑 Kitchen consumer shutting down")
        consumer.close()