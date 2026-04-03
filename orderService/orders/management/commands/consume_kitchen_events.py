from django.core.management.base import BaseCommand
from orders.kafka.kitchen_consumer import consume_kitchen_events


class Command(BaseCommand):
    help = "Consume kitchen events from Kafka and update order status"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🍽 Order Kafka consumer started")
        )
        consume_kitchen_events()