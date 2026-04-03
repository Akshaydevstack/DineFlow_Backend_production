import json
import logging
import signal

from django.conf import settings
from django.core.management.base import BaseCommand
from confluent_kafka import Consumer

from tickets.kafka.consumer import process_event

logger = logging.getLogger(__name__)

CONSUMER_NAME = "kitchen-dlq-replay"
DLQ_TOPIC = "kitchen.order.dlq"

running = True


# -----------------------------------
# Graceful shutdown
# -----------------------------------
def shutdown(signum, frame):
    global running
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


class Command(BaseCommand):
    help = "Replay Kitchen Order DLQ events"

    def handle(self, *args, **options):
        self.stdout.write("🔁 Kitchen Order DLQ replay started")

        consumer = Consumer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "group.id": CONSUMER_NAME,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })

        consumer.subscribe([DLQ_TOPIC])

        try:
            while running:
                msg = consumer.poll(1.0)

                if msg is None:
                    break

                if msg.error():
                    logger.error(msg.error())
                    continue

                try:
                    payload = json.loads(msg.value())

                    topic = payload["original_topic"]
                    event = payload["event"]
                    retry_count = payload.get("retry_count", 0)

                    process_event(event, topic)

                    consumer.commit(msg)

                    logger.info(
                        "✅ Replayed Kitchen DLQ event",
                        extra={
                            "topic": topic,
                            "order_id": event.get("order_id"),
                            "retry_count": retry_count,
                        },
                    )

                except Exception as e:
                    logger.exception(
                        "❌ Kitchen DLQ replay failed – message retained"
                    )
                   

        finally:
            consumer.close()
            self.stdout.write("🛑 Kitchen Order DLQ replay stopped")