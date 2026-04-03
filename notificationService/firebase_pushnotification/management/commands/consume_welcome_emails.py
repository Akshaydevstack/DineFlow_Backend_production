# notification_service/management/commands/consume_welcome_emails.py

from django.core.management.base import BaseCommand
from kafka.welcome_email_consumer import consume_user_created_events

class Command(BaseCommand):
    help = "Consume user.created events and enqueue welcome emails"

    def handle(self, *args, **options):
        consume_user_created_events()