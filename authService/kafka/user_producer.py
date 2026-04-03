from kafka.producer import get_producer
import json
import logging

logger = logging.getLogger(__name__)


def _delivery_report(err, msg):
    if err:
        logger.error(
            "user.created Kafka delivery failed",
            extra={
                "topic": msg.topic(),
                "key": msg.key(),
                "error": str(err),
            },
        )


def publish_user_created_event(*, user):
    producer = get_producer()
    restaurant = user.restaurant

    payload = {
        "user_id": user.public_id,
        "email": user.email,
        "name": user.first_name or "",
        "role": user.role,
        "restaurant_id": restaurant.public_id,
        "restaurant_name": restaurant.name,
        "created_at": user.created_at.isoformat(),
    }

    producer.produce(
        topic="user.created",
        key=user.public_id,
        value=json.dumps(payload).encode("utf-8"),
        on_delivery=_delivery_report,
    )

    producer.flush() 


# Django side (e.g., events.py or wherever your Kafka producers live)

def publish_user_updated_event(*, user):
    """
    Publishes an event when a user's details (like email or name) are updated.
    """
    producer = get_producer()
    restaurant = user.restaurant

    payload = {
        "user_id": user.public_id,
        "email": user.email,
        "name": user.first_name or "",
        "role": user.role,
        "restaurant_id": restaurant.public_id,
        "restaurant_name": restaurant.name,
        "created_at": user.created_at.isoformat(),
    }

    producer.produce(
        topic="user.updated",
        key=user.public_id,
        value=json.dumps(payload).encode("utf-8"),
        on_delivery=_delivery_report,
    )

    producer.flush()