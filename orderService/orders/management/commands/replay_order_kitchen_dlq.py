import json
import logging
import signal

from django.core.management.base import BaseCommand
from confluent_kafka import Consumer
from django.conf import settings

from orders.kafka.kitchen_consumer import process_event

logger = logging.getLogger(__name__)
running = True


def shutdown(signum, frame):
    global running
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


class Command(BaseCommand):
    help = "Replay Order Kitchen DLQ events"

    def handle(self, *args, **options):
        self.stdout.write("🔁 Order Kitchen DLQ replay started")

        consumer = Consumer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "group.id": "order-kitchen-dlq-replay",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })

        consumer.subscribe(["order.kitchen.dlq"])

        try:
            while running:
                msg = consumer.poll(1.0)
                if msg is None:
                    break

                payload = json.loads(msg.value())
                topic = payload["original_topic"]
                

                event = payload["event"]
                process_event(event, topic)

                consumer.commit(msg)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Replayed kitchen event | order_id={event.get('order_id')}"
                    )
                )

        finally:
            consumer.close()
            self.stdout.write("🛑 Kitchen DLQ replay stopped")