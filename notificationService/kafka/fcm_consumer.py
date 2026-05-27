import os
import json
import logging
import re
import signal
from contextlib import contextmanager

from confluent_kafka import Consumer
from django.conf import settings
from django.db import connection, transaction
from django.utils.timezone import now

from firebase_pushnotification.models import Notification
from firebase_pushnotification.services.fcm_service import send_push_notification_task
from kafka.producer import get_producer
from kafka.dlq_producer import send_to_dlq

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

channel_layer = get_channel_layer()

logger = logging.getLogger("notification.consumer")

# --------------------------------------------------
# Config
# --------------------------------------------------
MAX_RETRIES = 3
DLQ_TOPIC = "notification.dlq"
CONSUMER_NAME = "notification-consumer"
running = True

# 🟢 FIX 1: Standardized regex and service name for isolation
TENANT_REGEX = re.compile(r"^rest_[a-z0-9]+$")
SERVICE_NAME = os.getenv("SERVICE_NAME", "notification")


# ----------------------------
# Graceful shutdown
# ----------------------------
def shutdown(signum, frame):
    global running
    logger.warning("🛑 Shutdown signal received")
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# ----------------------------
# Kafka Consumer
# ----------------------------
consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKER,
    "group.id": CONSUMER_NAME,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

consumer.subscribe([
    "orders.placed",
    "orders.cancelled",
    "kitchen.ticket.accepted",
    "kitchen.ticket.preparing",
    "kitchen.ticket.ready",
    "kitchen.ticket.cancelled",
    "kitchen.ticket.created"
])


TOPIC_TO_NOTIFICATION = {
    "orders.placed": ("Order Placed", "Your order has been placed 🎉"),
    "orders.cancelled": ("Order Cancelled", "Your order was cancelled ❌"),
    "kitchen.ticket.accepted": ("Order Accepted", "Kitchen accepted your order 👨‍🍳"),
    "kitchen.ticket.preparing": ("Order Preparing", "Your order is being prepared 🍳"),
    "kitchen.ticket.ready": ("Order Ready", "Your order is ready 🍽️"),
    "kitchen.ticket.cancelled": ("Order Cancelled", "Kitchen cancelled your order ❌"),
    "kitchen.ticket.created": ("Kitchen ticket create", "Kitchen created a new ticket")
}


# --------------------------------------------------
# Tenant schema helper (Supabase Pooler Safe)
# --------------------------------------------------
@contextmanager
def tenant_schema(restaurant_id: str):
    """
    Safely switches to a tenant's schema using a transaction-bound SET LOCAL.
    """
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


# ----------------------------
# Event processing
# ----------------------------
def process_event(event: dict, topic: str):
    if topic not in TOPIC_TO_NOTIFICATION:
        logger.info("⏭️ Skipping unsupported topic", extra={"topic": topic})
        return

    restaurant_id = event.get("restaurant_id")
    user_id = event.get("user_id") or event.get("customer_id")

    if not restaurant_id or not user_id:
        raise ValueError("restaurant_id or user_id missing")

    title, body = TOPIC_TO_NOTIFICATION[topic]

    logger.info(
        "📩 Processing notification",
        extra={
            "topic": topic,
            "restaurant_id": restaurant_id,
            "user_id": user_id,
        },
    )

    # 🟢 FIX 2: Use the context manager for database operations ONLY
    with tenant_schema(restaurant_id):
        # We don't need a second transaction.atomic() here because 
        # the tenant_schema context manager already wraps this in one!
        Notification.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            topic=topic,
            reference_id=event.get("order_id"),
            created_at=now(),
        )

    # 🟢 FIX 3: Push tasks OUTSIDE the DB context block
    # By un-indenting, we release the PostgreSQL connection back to the Supabase pooler
    # BEFORE we spend time talking to Redis or Firebase. 

    # Queue FCM push
    send_push_notification_task.delay(
        user_id=user_id,
        restaurant_id=restaurant_id,
        title=title,
        body=body,
    )
    logger.info(f"✅ Notification stored & queued {topic}")

    # -------------------------------------------------
    # 🔴 Realtime WebSocket Push (Kitchen Display)
    # -------------------------------------------------
    if topic in {"kitchen.ticket.created", "kitchen.ticket.cancelled"}:
        try:
            async_to_sync(channel_layer.group_send)(
                f"kitchen_display_{restaurant_id}",
                {
                    "type": "send_ticket_update",
                    "data": event,
                },
            )

            logger.info(
                "📡 Realtime kitchen update sent",
                extra={
                    "restaurant_id": restaurant_id,
                    "topic": topic,
                },
            )
        except Exception as e:
            logger.exception(
                "❌ Failed to send realtime kitchen update",
                extra={
                    "restaurant_id": restaurant_id,
                    "topic": topic,
                    "error": str(e),
                },
            )


# ----------------------------
# Main consume loop
# ----------------------------
def consume_notification_events():
    logger.info("🚀 Notification Kafka consumer started")

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error("❌ Kafka error", extra={"error": str(msg.error())})
                continue

            headers = dict(msg.headers() or {})
            retry_count = int((headers.get("retry_count") or b"0").decode())

            try:
                event = json.loads(msg.value())
                process_event(event, msg.topic())
                consumer.commit(msg)

            except Exception as e:
                logger.warning(
                    f"⚠️ Processing failed for topic {msg.topic()}: {str(e)}", 
                    extra={
                        "topic": msg.topic(),
                        "retry": retry_count,
                    },
                )

                if retry_count < MAX_RETRIES:
                    producer = get_producer()
                    producer.produce(
                        topic=msg.topic(),
                        key=msg.key(),
                        value=msg.value(),
                        headers={"retry_count": str(retry_count + 1)},
                    )
                    producer.poll(0)

                    logger.warning(
                        "🔁 Retrying message",
                        extra={
                            "topic": msg.topic(),
                            "next_retry": retry_count + 1,
                        },
                    )
                else:
                    send_to_dlq(
                        topic=msg.topic(),
                        event=event,
                        error=e,
                        consumer=CONSUMER_NAME,
                        dlq_topic=DLQ_TOPIC,
                        key=msg.key(),
                        retry_count=retry_count,
                    )

                    logger.error(
                        "☠️ Sent to DLQ",
                        extra={
                            "topic": msg.topic(),
                            "retry": retry_count,
                            "dlq": DLQ_TOPIC,
                        },
                    )

                consumer.commit(msg)

    finally:
        consumer.close()
        logger.info("🛑 Notification consumer stopped")