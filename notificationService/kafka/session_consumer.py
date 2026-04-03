import json
import logging
import signal

from confluent_kafka import Consumer
from django.conf import settings

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from kafka.producer import get_producer
from kafka.dlq_producer import send_to_dlq


logger = logging.getLogger("session.consumer")

channel_layer = get_channel_layer()

MAX_RETRIES = 3
DLQ_TOPIC = "table-session.dlq"
CONSUMER_NAME = "table-session-consumer"

running = True


# -------------------------------------------------
# Graceful shutdown
# -------------------------------------------------

def shutdown(signum, frame):
    global running
    logger.warning("🛑 Shutdown signal received")
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# -------------------------------------------------
# Kafka Consumer
# -------------------------------------------------

consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKER,
    "group.id": CONSUMER_NAME,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})


consumer.subscribe([
    "table.session.started",
    "table.session.closed",
])


# -------------------------------------------------
# WebSocket Event Processing
# -------------------------------------------------

def process_event(event: dict):

    restaurant_id = event.get("restaurant_id")

    if not restaurant_id:
        raise ValueError("restaurant_id missing")

    group = f"waiter_table_sessions_{restaurant_id}"

    logger.info(
        "📡 Dispatching websocket session update",
        extra={
            "restaurant_id": restaurant_id,
            "event_type": event.get("event_type"),
            "session_id": event.get("session_id"),
        },
    )

    async_to_sync(channel_layer.group_send)(
        group,
        {
            "type": "send_session_update",
            "data": event,
        },
    )

    logger.info(
        "✅ WebSocket session update sent",
        extra={
            "restaurant_id": restaurant_id,
            "session_id": event.get("session_id"),
        },
    )


# -------------------------------------------------
# Main consume loop
# -------------------------------------------------

def consume_table_sessions():

    logger.info("🚀 Table Session Kafka consumer started")

    try:

        while running:

            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(
                    "❌ Kafka consumer error",
                    extra={"error": str(msg.error())},
                )
                continue

            headers = dict(msg.headers() or {})
            retry_count = int((headers.get("retry_count") or b"0").decode())

            try:

                event = json.loads(msg.value())

                logger.info(
                    "📥 Kafka event received",
                    extra={
                        "topic": msg.topic(),
                        "session_id": event.get("session_id"),
                        "event_type": event.get("event_type"),
                    },
                )

                process_event(event)

                consumer.commit(msg)

            except Exception as e:

                logger.warning(
                    "⚠️ Processing failed",
                    extra={
                        "topic": msg.topic(),
                        "retry": retry_count,
                        "error": str(e),
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

        logger.info("🛑 Table session consumer stopped")