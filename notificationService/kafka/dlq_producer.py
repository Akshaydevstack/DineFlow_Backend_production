import json
import logging
from kafka.producer import get_producer

logger = logging.getLogger(__name__)


def send_to_dlq(
    *,
    topic: str,
    event: dict,
    error: Exception,
    consumer: str,
    dlq_topic: str,
    key: str | None = None,
    retry_count: int = 0,
):
    payload = {
        "original_topic": topic,
        "event": event,
        "error": str(error),
        "consumer": consumer,
        "retry_count": retry_count,
    }

    producer = get_producer()
    producer.produce(
        topic=dlq_topic,
        key=key,
        value=json.dumps(payload),
    )
    producer.poll(0)

    logger.error(
        f"☠️ Sent to DLQ {dlq_topic} | topic={topic} | retry={retry_count}"
    )