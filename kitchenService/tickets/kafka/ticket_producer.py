import json
import logging
from django.utils import timezone
from tickets.kafka.producer import get_producer

logger = logging.getLogger(__name__)


def publish_kitchen_ticket_event(event_type: str, ticket):
    """
    Generic publisher for kitchen ticket events.

    event_type examples:
        CREATED
        UPDATED
        CANCELLED
        READY
    """

    producer = get_producer()

    topic_name = f"kitchen.ticket.{event_type.lower()}"

    event = {
        "event_type": f"KITCHEN_TICKET_{event_type.upper()}",
        "public_id": str(ticket.public_id),
        "order_id": ticket.order_id,
        "user_id": ticket.user_id,
        "restaurant_id": ticket.restaurant_id,
        "status": ticket.status,
        "items": [
            {
                "dish_id": item.dish_id,
                "dish_name": item.dish_name,
                "quantity": item.quantity,
            }
            for item in ticket.items.all()
        ],
        "created_at": timezone.now().isoformat(),
    }

    try:
        producer.produce(
            topic=topic_name,
            key=str(ticket.order_id),
            value=json.dumps(event),
        )

        producer.flush()

        logger.info(
            f"✅ Published {topic_name} for order {ticket.order_id}"
        )

    except Exception:
        logger.exception(f"❌ Failed to publish {topic_name}")
        raise