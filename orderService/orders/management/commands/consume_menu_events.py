from django.core.management.base import BaseCommand
from orders.kafka.menu_consumer import consume_menu_events


class Command(BaseCommand):
    help = "Consume menu events from Kafka and update order menu snapshots"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🧾 Order Menu Kafka consumer started")
        )
        consume_menu_events()