from django.core.management.base import BaseCommand
from django.db import connection
from dishes.models import Dish


class Command(BaseCommand):
    help = "Backfill menu_version for dishes in a restaurant schema"

    def add_arguments(self, parser):
        parser.add_argument(
            "restaurant_id",
            type=str,
            help="Restaurant schema name (e.g. rest_7c73c842)",
        )
        parser.add_argument(
            "--menu-version",
            dest="menu_version",
            default="v1",
            help="Menu version to assign (default: v1)",
        )

    def handle(self, *args, **options):
        restaurant_id = options["restaurant_id"]
        menu_version = options["menu_version"]

        self.stdout.write(
            f"🔁 Switching to schema: {restaurant_id}"
        )

        with connection.cursor() as cursor:
            cursor.execute(
                f'SET search_path TO "{restaurant_id}", public'
            )

        updated = Dish.objects.filter(
            menu_version__isnull=True
        ).update(
            menu_version=menu_version
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Updated {updated} dishes "
                f"with menu_version={menu_version}"
            )
        )