import json
import logging
from confluent_kafka import Producer
from django.conf import settings
from django.utils.timezone import now

logger = logging.getLogger(__name__)

_dlq_producer = None


def get_dlq_producer():
    global _dlq_producer
    if _dlq_producer is None:
        _dlq_producer = Producer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "acks": "all",
            "linger.ms": 10,
        })
    return _dlq_producer


def send_to_dlq(
    *,
    topic: str,
    event: dict,
    error: Exception,
    consumer: str,
    dlq_topic: str,
    key: str | None = None,
    retry_count: int | None = None,
):
    producer = get_dlq_producer()

    payload = {
        "service": consumer,
        "original_topic": topic,
        "error": str(error),
        "event": event,
        "retry_count": retry_count,
        "occurred_at": now().isoformat(),
    }

    try:
        producer.produce(
            topic=dlq_topic,
            key=key,
            value=json.dumps(payload),
            headers={
                "consumer": consumer,
                "retry_count": str(retry_count or 0),
            },
        )

        producer.flush()

        logger.error(
            f"Sent event to DLQ topic={dlq_topic} from topic={topic}",
            extra={
                "consumer": consumer,
                "retry_count": retry_count,
            },
        )

    except Exception as e:
        logger.exception(
            f"Failed to send message to DLQ topic={dlq_topic}"
        )