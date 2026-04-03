from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command
import time

# 🔥 Tune based on DB capacity
BATCH_SIZE = 50        # 25–100 is safe
SLEEP_SECONDS = 0.5   # Small pause to avoid DB overload


class Command(BaseCommand):
    help = "Safely migrate all tenant schemas in batches"

    def handle(self, *args, **options):
        self.stdout.write("\n🚀 Starting batch-safe tenant migrations...")

        tenant_schemas = self.get_tenant_schemas()
        total = len(tenant_schemas)

        if total == 0:
            self.stdout.write("ℹ️ No tenant schemas found")
            return

        self.stdout.write(f"📦 Found {total} tenant schemas")

        for i in range(0, total, BATCH_SIZE):
            batch = tenant_schemas[i:i + BATCH_SIZE]

            self.stdout.write(
                f"\n🔁 Migrating batch {i // BATCH_SIZE + 1} "
                f"({i + 1} → {i + len(batch)})"
            )

            for schema in batch:
                self.migrate_schema(schema)

            # 🔥 Cool-down between batches
            time.sleep(SLEEP_SECONDS)

        self.stdout.write("\n✅ All tenant schemas migrated successfully\n")

    # --------------------------------------------------

    def get_tenant_schemas(self):
        """
        Fetch all tenant schemas (rest_*)
        """
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name LIKE 'rest_%'
                ORDER BY schema_name
            """)
            return [row[0] for row in cursor.fetchall()]

    # --------------------------------------------------

    def migrate_schema(self, schema_name):
        """
        Run migrations for a single tenant schema
        """
        try:
            self.stdout.write(f"   🔄 Migrating {schema_name}")

            # Switch schema
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SET search_path TO "{schema_name}", public'
                )

            # Run Django migrations
            call_command(
                "migrate",
                interactive=False,
                verbosity=0,
            )

        except Exception as e:
            # ❌ Do NOT stop other tenants
            self.stderr.write(
                f"   ❌ Failed migrating {schema_name}: {str(e)}"
            )

        finally:
            # Always reset schema
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")