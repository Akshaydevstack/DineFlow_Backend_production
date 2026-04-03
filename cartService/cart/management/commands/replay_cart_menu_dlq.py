import json
import logging
import signal

from django.conf import settings
from django.core.management.base import BaseCommand
from confluent_kafka import Consumer

from cart.kafka.menu_consumer import process_event

logger = logging.getLogger(__name__)

RUNNING = True


# --------------------------------------------------
# Graceful shutdown
# --------------------------------------------------
def shutdown(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


class Command(BaseCommand):
    help = "Replay Cart Menu DLQ events"

    def handle(self, *args, **options):
        self.stdout.write("🔁 Cart Menu DLQ replay started")

        consumer = Consumer({
            "bootstrap.servers": settings.KAFKA_BROKER,
            "group.id": "cart-menu-dlq-replay",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })

        # ✅ NEW DLQ TOPIC
        consumer.subscribe([
            getattr(settings, "CART_MENU_DLQ_TOPIC", "cart.menu.dlq")
        ])

        try:
            while RUNNING:
                msg = consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error(msg.error())
                    continue

                try:
                    payload = json.loads(msg.value())

                    topic = payload["original_topic"]
                    event = payload["event"]
                    retry_count = payload.get("retry_count")

                    process_event(event, topic)

                    consumer.commit(msg)

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Replayed Cart Menu DLQ | "
                            f"topic={topic}, "
                            f"dish_id={event.get('dish_id')}, "
                            f"retry_count={retry_count}"
                        )
                    )

                except Exception as e:
                    logger.exception("❌ Cart Menu DLQ replay failed")
                    self.stdout.write(
                        self.style.ERROR(
                            f"❌ Replay failed, message kept in DLQ: {e}"
                        )
                    )
                    # ❗ DO NOT commit → message stays for retry

        finally:
            consumer.close()
            self.stdout.write(
                self.style.WARNING("🛑 Cart Menu DLQ replay stopped")
            )