import json
import logging
from confluent_kafka import Producer
from django.conf import settings

logger = logging.getLogger(__name__)

_producer = None


def get_producer():
    global _producer
    if _producer is None:
        _producer = Producer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "acks": "all",
            "retries": 3,
            "linger.ms": 10,
            "enable.idempotence": True,
        })
    return _producer


def _delivery_report(err, msg):
    if err:
        logger.error(f"Kafka delivery failed: {err}")


def publish_kitchen_event(event_type, ticket):
    producer = get_producer()

    event = {
        "event_type": event_type,
        "order_id": ticket.order_id,
        "user_id": ticket.user_id,
        "restaurant_id": ticket.restaurant_id,
        "status": ticket.status,
        "occurred_at": ticket.updated_at.isoformat(),
    }

    producer.produce(
        topic=f"kitchen.ticket.{event_type.lower()}",
        key=ticket.order_id,
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.flush()