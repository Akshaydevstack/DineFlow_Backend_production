import json
import logging
from kafka.producer import get_producer

logger = logging.getLogger(__name__)

def _restaurant_delivery_report(err, msg):
    if err:
        logger.error(
            "Restaurant Kafka delivery failed",
            extra={
                "topic": msg.topic(),
                "key": msg.key(),
                "error": str(err),
            },
        )

def publish_restaurant_event(restaurant, event_type):
    """
    Publishes the restaurant data to Kafka.
    event_type should be 'restaurant.created' or 'restaurant.updated'
    """
    producer = get_producer()

    # Format time and decimal fields safely for JSON serialization
    opening_time = restaurant.opening_time.strftime('%H:%M:%S') if restaurant.opening_time else None
    closing_time = restaurant.closing_time.strftime('%H:%M:%S') if restaurant.closing_time else None
    lat = float(restaurant.latitude) if restaurant.latitude else None
    lon = float(restaurant.longitude) if restaurant.longitude else None

    # We extract all the fields the Vector DB needs for semantic search
    payload = {
        "public_id": restaurant.public_id,
        "name": restaurant.name,
        "slug": restaurant.slug,
        "address": restaurant.address,
        "city": restaurant.city,
        "state": restaurant.state,
        "pincode": restaurant.pincode,
        "latitude": lat,
        "longitude": lon,
        "phone": restaurant.phone,
        "email": restaurant.email,
        "is_open": restaurant.is_open,
        "is_active": restaurant.is_active,
        "opening_time": opening_time,
        "closing_time": closing_time,
        "restaurant_version": restaurant.restaurant_version,
        "updated_at": restaurant.updated_at.isoformat(),
    }

    producer.produce(
        topic=event_type,
        key=restaurant.public_id,
        value=json.dumps(payload).encode("utf-8"),
        on_delivery=_restaurant_delivery_report,
    )

    producer.flush()