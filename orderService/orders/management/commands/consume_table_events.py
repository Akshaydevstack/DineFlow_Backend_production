from django.core.management.base import BaseCommand
from orders.kafka.table_consumer import consume_table_events


class Command(BaseCommand):
    help = "Consume restaurant table events from Kafka and update order table snapshots"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🪑 Order Table Kafka consumer started")
        )
        consume_table_events()