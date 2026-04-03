from django.core.management.base import BaseCommand
from kafka.table_session_consumer import consume_table_session_events


class Command(BaseCommand):
    help = "Start Kafka consumer for table session events"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🪑 Starting Table Session Consumer...")
        )

        consume_table_session_events()