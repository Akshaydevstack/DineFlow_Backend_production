from django.core.management.base import BaseCommand
from tickets.kafka.consumer import consume_order_events


class Command(BaseCommand):
    help = "Consume order events from Kafka"

    def handle(self, *args, **options):
        consume_order_events()