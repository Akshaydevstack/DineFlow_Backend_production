from kafka.producer import get_producer
import json
import logging

logger = logging.getLogger(__name__)


def _delivery_report(err, msg):
    if err:
        logger.error(
            "restaurant.table.upsert Kafka delivery failed",
            extra={
                "topic": msg.topic(),
                "key": msg.key(),
                "error": str(err),
            },
        )


def publish_table_upsert_event(*, table):
    producer = get_producer()

    payload = {
        "event_type": "TABLE_UPSERT",
        "restaurant_id": table.restaurant.public_id,
        "restaurant_name": table.restaurant.name,
        "table_public_id": table.public_id,
        "table_number": table.table_number,
        "zone_public_id": table.zone.public_id if table.zone else None,
        "zone_name": table.zone.name if table.zone else None,
        "is_active": table.is_active,
        "table_type": table.table_type,
        "occurred_at": table.updated_at.isoformat(),
        "version": table.table_version,
    }

    producer.produce(
        topic="restaurant.table.upsert",
        key=table.public_id,
        value=json.dumps(payload).encode("utf-8"),
        on_delivery=_delivery_report,
    )

    producer.flush()