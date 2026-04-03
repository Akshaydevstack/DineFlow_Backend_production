import json
import logging
import signal

from confluent_kafka import Consumer
from django.conf import settings


from email_service.tasks import send_welcome_email_to_sqs

logger = logging.getLogger("welcome_email.consumer")

CONSUMER_GROUP = "welcome-email-consumer"
TOPIC = "user.created"
running = True


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
    "group.id": CONSUMER_GROUP,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,  
})


consumer.subscribe([TOPIC])


# ----------------------------
# Main consume loop
# ----------------------------
def consume_user_created_events():
    logger.info("🚀 Welcome Email consumer started")

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error("❌ Kafka error", extra={"error": str(msg.error())})
                continue

            try:
                event = json.loads(msg.value())

                logger.info(
                    "📨 user.created received",
                    extra={
                        "user_id": event.get("user_id"),
                        "email": event.get("email"),
                        "restaurant": event.get("restaurant_name"),
                    },
                )

                send_welcome_email_to_sqs.delay(
                    email=event["email"],
                    name=event.get("name", ""),
                    restaurant=event["restaurant_name"],
                )

                logger.info(
                    "📬 Welcome email enqueued",
                    extra={
                        "email": event["email"],
                        "restaurant": event["restaurant_name"],
                    },
                )

            except Exception as e:
                logger.exception(
                    "⚠️ Failed to enqueue welcome email (ignored)",
                    extra={"raw": msg.value()},
                )

    finally:
        consumer.close()
        logger.info("🛑 Welcome Email consumer stopped")