import json
import boto3
import os
import logging
from celery import shared_task

logger = logging.getLogger(__name__)

WELCOME_EMAIL_QUEUE_URL = os.environ.get(
    "WELCOME_EMAIL_QUEUE_URL", 
    "https://sqs.ap-south-1.amazonaws.com/660119432940/welcome-email-queue"
)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_welcome_email_to_sqs(self, email: str, name: str, restaurant: str):
    if not email:
        logger.warning("Skipping SQS send: email missing")
        return

    # 🚀 Initialize inside the task for Celery thread-safety
    # Boto3 automatically finds AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the environment
    sqs = boto3.client(
        "sqs", 
        region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")
    )

    payload = {
        "email": email,
        "name": name,
        "restaurant": restaurant,
    }

    sqs.send_message(
        QueueUrl=WELCOME_EMAIL_QUEUE_URL,
        MessageBody=json.dumps(payload),
    )

    # 🚀 Formatted string so it actually prints to your Kubernetes logs!
    logger.info(
        f"📤 Welcome email pushed to SQS | email={email} | restaurant={restaurant}",
        extra={"email": email, "restaurant": restaurant},
    )