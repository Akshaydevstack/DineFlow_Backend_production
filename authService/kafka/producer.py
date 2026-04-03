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
            "linger.ms": 10,
            "retries": 3,
        })

    return _producer