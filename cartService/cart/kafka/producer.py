import json
import logging
from confluent_kafka import Producer
from django.conf import settings
from django.utils.timezone import now

logger = logging.getLogger(__name__)

_producer = None


def get_producer():
    """
    Singleton Kafka producer for cart-service
    """
    global _producer
    if _producer is None:
        _producer = Producer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "acks": "all",
            "retries": 3,
            "linger.ms": 10,
        })
    return _producer


def _delivery_report(err, msg):
    if err is not None:
        logger.error(
            "❌ Cart Kafka delivery failed",
            extra={
                "topic": msg.topic(),
                "key": msg.key(),
                "error": str(err),
            },
        )


def publish_cart_event(
    *,
    event_type: str,
    restaurant_id: str,
    user_id: str,
    cart_payload: dict,
):
    """
    Generic cart event publisher
    """
    producer = get_producer()

    event = {
        "event_version": 1,
        "event_type": event_type,
        "restaurant_id": restaurant_id,
        "user_id": user_id,
        "cart": cart_payload,
        "occurred_at": now().isoformat(),
    }

    producer.produce(
        topic=f"cart.{event_type.lower()}",
        key=f"{restaurant_id}:{user_id}",
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.flush()

    logger.info(
        f"📦 Cart event published | type={event_type} "
        f"user={user_id} restaurant={restaurant_id}"
    )