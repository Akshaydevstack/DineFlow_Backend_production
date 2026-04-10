from django.core.management.base import BaseCommand
from orders.kafka.restaurant_consumer import consume_restaurant_events

class Command(BaseCommand):
    help = 'Starts the Kafka consumer for Restaurant read-replica updates'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting order-restaurant-consumer...'))
        consume_restaurant_events()