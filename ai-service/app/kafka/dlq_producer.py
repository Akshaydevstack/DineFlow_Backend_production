# app/kafka/dlq_producer.py
import json

from loguru import logger
import os

from confluent_kafka import Producer



# --------------------------------------------------
# Config
# --------------------------------------------------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# --------------------------------------------------
# Producer — reuse single instance
# --------------------------------------------------
producer = Producer({
    "bootstrap.servers": KAFKA_BOOTSTRAP,
})


# --------------------------------------------------
# Delivery callback — logs success / failure
# --------------------------------------------------
def _delivery_report(err, msg):
    if err:
        logger.error(
            f"❌ DLQ delivery failed | "
            f"topic={msg.topic()} | error={err}"
        )
    else:
        logger.info(
            f"📨 DLQ delivery confirmed | "
            f"topic={msg.topic()} | partition={msg.partition()} | offset={msg.offset()}"
        )


# --------------------------------------------------
# send_to_dlq
# --------------------------------------------------
def send_to_dlq(
    topic: str,
    event: dict,
    error: Exception,
    consumer: str,
    dlq_topic: str,
    key: str = None,
):
    """
    Send a failed event to the DLQ topic.
    Same pattern as your Django cart DLQ producer.

    Args:
        topic      : original topic where message came from
        event      : the raw event dict that failed
        error      : the exception that was raised
        consumer   : consumer name for tracing (e.g. "ai-service-consumer")
        dlq_topic  : destination DLQ topic (e.g. "ai.service.dlq")
        key        : message key for partitioning (dish_id or order_id)
    """
    try:
        payload = {
            "original_topic": topic,
            "consumer":       consumer,
            "error":          str(error),
            "error_type":     type(error).__name__,
            "event":          event,
        }

        producer.produce(
            dlq_topic,
            value=json.dumps(payload).encode("utf-8"),
            key=key.encode("utf-8") if key else None,
            callback=_delivery_report,
        )

        # Wait for delivery confirmation
        producer.flush()

    except Exception as e:
        # DLQ itself failed — just log, never raise
        # We don't want DLQ failure to break the consumer loop
        logger.exception(
            f"🔥 Failed to send to DLQ | "
            f"dlq_topic={dlq_topic} | original_topic={topic} | error={e}"
        )