import json
import logging
from confluent_kafka import Producer
from django.conf import settings
from django.utils.timezone import now

logger = logging.getLogger(__name__)

_producer = None


def get_producer():
    global _producer
    if _producer is None:
        _producer = Producer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "acks": "all",
            "linger.ms": 10,
            "retries": 3,
        })
    return _producer


def _delivery_report(err, msg):
    if err:
        logger.error(
            "Menu Kafka delivery failed",
            extra={"topic": msg.topic(), "error": str(err)},
        )
    else:
        # Add this so you can see it in your kubectl logs!
        print(f"✅ SUCCESSFULLY SENT to {msg.topic()} partition [{msg.partition()}]")

def publish_menu_item_event(event_type: str, dish_data: dict):
    producer = get_producer()

    event = {
        "event_version": 1,
        "event_type": event_type,

        # ======================
        # IDENTIFIERS
        # ======================
        "restaurant_id": dish_data["restaurant_id"],
        "dish_id": dish_data["dish_id"],

        # ======================
        # CORE
        # ======================
        "name": dish_data.get("name"),
        "description": dish_data.get("description"),

        # ======================
        # CATEGORY
        # ======================
        "category_id": dish_data.get("category_id"),
        "category_name": dish_data.get("category_name"),

        # ======================
        # PRICING
        # ======================
        "price": str(dish_data.get("price")) if dish_data.get("price") else None,
        "original_price": (
            str(dish_data.get("original_price"))
            if dish_data.get("original_price")
            else None
        ),

        # ======================
        # ATTRIBUTES (AI CRITICAL)
        # ======================
        "is_veg": dish_data.get("is_veg", False),
        "is_spicy": dish_data.get("is_spicy", False),
        "is_popular": dish_data.get("is_popular", False),
        "is_trending": dish_data.get("is_trending", False),
        "is_quick_bites": dish_data.get("is_quick_bites", False),

        # ======================
        # QUALITY SIGNALS
        # ======================
        "average_rating": float(dish_data.get("average_rating", 0)),
        "review_count": dish_data.get("review_count", 0),
        "total_orders": dish_data.get("total_orders", 0),

        # ======================
        # OPERATIONS
        # ======================
        "is_available": dish_data.get("is_available", True),
        "prep_time": dish_data.get("prep_time"),
        "priority": dish_data.get("priority", 0),

        # ======================
        # MEDIA
        # ======================
        "image_url": dish_data.get("image_url"),

        # ======================
        # VERSIONING
        # ======================
        "menu_version": dish_data["menu_version"],
        "occurred_at": dish_data.get("occurred_at"),
    }

    producer.produce(
        topic=f"menu.item.{event_type.lower()}",
        key=dish_data["dish_id"],
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.flush()