import json
import logging
import re
import signal
from django.utils.dateparse import parse_datetime
from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from django.core.exceptions import ValidationError

from orders.models import Order
from orders.kafka.producer import get_producer
from orders.kafka.dlq_producer import send_to_dlq

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
TENANT_REGEX = re.compile(r"^[a-z][a-z0-9_]+$")
ORDER_KITCHEN_DLQ_TOPIC = "order.kitchen.dlq"
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
# Kafka consumer
# --------------------------------------------------
consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKER,
    "group.id": "order-kitchen-consumer",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

consumer.subscribe([
    "kitchen.ticket.accepted",
    "kitchen.ticket.preparing",
    "kitchen.ticket.ready",
    "kitchen.ticket.cancelled",
])


TOPIC_TO_STATUS = {
    "kitchen.ticket.accepted": Order.STATUS_ACCEPTED,
    "kitchen.ticket.preparing": Order.STATUS_PREPARING,
    "kitchen.ticket.ready": Order.STATUS_READY,
    "kitchen.ticket.cancelled": Order.STATUS_CANCELLED,
}


# --------------------------------------------------
# Schema helpers
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
    if topic not in TOPIC_TO_STATUS:
        raise ValueError(f"Unknown topic: {topic}")

    restaurant_id = event["restaurant_id"]
    order_id = event["order_id"]
    new_status = TOPIC_TO_STATUS[topic]

    occurred_at = (
        parse_datetime(event.get("occurred_at"))
        if event.get("occurred_at")
        else None
    )

    _set_schema(restaurant_id)
    
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(
                public_id=order_id
            )

            if order.status == new_status:
                logger.info(
                    f"↩️ Order {order_id} already {new_status}, skipping"
                )
                return

            order.update_status(new_status, occurred_at)
            logger.info(
                f"✅ Order {order_id} → {new_status}"
            )

    finally:
        _reset_schema()


# --------------------------------------------------
# Main consumer loop
# --------------------------------------------------
def consume_kitchen_events():
    logger.info("📦 Order Kitchen Kafka consumer started")

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
            # Non-retriable → DLQ
            # -------------------------
            except (Order.DoesNotExist, ValidationError) as e:
                logger.warning(
                    f"❌ Non-retriable error for order "
                    f"{event.get('order_id')}: {e}"
                )

                send_to_dlq(
                    topic=topic,
                    event=event,
                    error=e,
                    consumer="kitchen-order-consumer",
                    dlq_topic=ORDER_KITCHEN_DLQ_TOPIC,  # kitchen.dlq
                    key=event.get("order_id"),
                    retry_count=retry_count,
                )

                consumer.commit(msg)

            # -------------------------
            # Retriable
            # -------------------------
            except Exception as e:
                if retry_count < MAX_RETRIES:
                    logger.warning(
                        f"🔁 Retrying {topic} for order "
                        f"{event.get('order_id')} "
                        f"({retry_count + 1}/{MAX_RETRIES})"
                    )

                    producer = get_producer()
                    producer.produce(
                        topic=topic,
                        key=msg.key(),
                        value=msg.value(),
                        headers={
                            "retry_count": str(retry_count + 1)
                        },
                    )
                    producer.poll(0)

                else:
                    logger.error(
                        f"☠️ Max retries exceeded for order "
                        f"{event.get('order_id')}"
                    )

                    send_to_dlq(
                        topic=topic,
                        event=event,
                        error=e,
                        consumer="kitchen-order-consumer",
                        dlq_topic=ORDER_KITCHEN_DLQ_TOPIC, 
                        key=event.get("order_id"),
                        retry_count=retry_count,
                    )
                consumer.commit(msg)

    finally:
        logger.info("🛑 Order Kitchen consumer shutting down")
        consumer.close()
