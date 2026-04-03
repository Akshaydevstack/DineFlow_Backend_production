from django.core.management.base import BaseCommand
from django.db import connection
from dishes.models import Dish

class Command(BaseCommand):
    help = "Backfill restaurant_id for dishes in a schema"

    def add_arguments(self, parser):
        parser.add_argument("restaurant_id")

    def handle(self, *args, **options):
        restaurant_id = options["restaurant_id"]

        with connection.cursor() as cursor:
            cursor.execute(
                f'SET search_path TO "{restaurant_id}", public'
            )

        updated = Dish.objects.filter(
            restaurant_id__isnull=True
        ).update(
            restaurant_id=restaurant_id
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Updated {updated} dishes in schema {restaurant_id}"
            )
        )