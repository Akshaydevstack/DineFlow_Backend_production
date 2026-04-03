import json
import logging
import re
import signal

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
TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")
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
# Event processor
# --------------------------------------------------
def process_event(event: dict, topic: str):
    restaurant_id = event.get("restaurant_id")
    if not restaurant_id:
        raise ValueError("restaurant_id missing in event")

    _set_schema(restaurant_id)

    try:
        if topic == "orders.placed":

            with transaction.atomic():
                ticket = handle_order_placed(event, restaurant_id)

                if ticket:
                    transaction.on_commit(
                        lambda: publish_kitchen_ticket_event("CREATED", ticket)
                    )
        elif topic == "orders.cancelled":

            with transaction.atomic():
                ticket = handle_order_cancelled(event)

                transaction.on_commit(
                    lambda: publish_kitchen_ticket_event("CANCELLED", ticket)
                )

        else:
            raise ValueError(f"Unknown topic: {topic}")

    finally:
        _reset_schema()


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
