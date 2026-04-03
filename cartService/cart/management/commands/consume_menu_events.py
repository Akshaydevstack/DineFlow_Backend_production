from django.core.management.base import BaseCommand
from cart.kafka.menu_consumer import consume_menu_events


class Command(BaseCommand):
    help = "Consume menu item events and update cart menu snapshots"

    def handle(self, *args, **options):
        self.stdout.write("🛒 Cart Menu Snapshot Kafka consumer started")
        consume_menu_events()