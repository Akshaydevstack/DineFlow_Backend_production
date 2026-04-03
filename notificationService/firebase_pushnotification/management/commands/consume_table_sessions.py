from django.core.management.base import BaseCommand
from kafka.session_consumer import consume_table_sessions

class Command(BaseCommand):

    help = "Run table session Kafka consumer"

    def handle(self, *args, **kwargs):

        self.stdout.write("Starting session consumer...")

        consume_table_sessions()