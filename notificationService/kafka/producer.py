from confluent_kafka import Producer
from django.conf import settings

_producer = None


def get_producer():
    global _producer

    if _producer is None:
        _producer = Producer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "linger.ms": 10,
            "acks": "all",
        })

    return _producer