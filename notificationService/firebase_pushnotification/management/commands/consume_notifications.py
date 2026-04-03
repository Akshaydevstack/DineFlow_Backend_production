from django.core.management.base import BaseCommand
from kafka.fcm_consumer import consume_notification_events


class Command(BaseCommand):
    help = "Consume notification Kafka events"

    def handle(self, *args, **options):
        consume_notification_events()