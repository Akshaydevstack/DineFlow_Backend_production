import logging
from celery import shared_task
from firebase_admin import messaging

from firebase_pushnotification.models import DeviceToken
from firebase_pushnotification.db.schema import set_schema, reset_schema

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)

def send_push_notification_task(
    self,
    *,
    user_id: str,
    restaurant_id: str,
    title: str,
    body: str,
):
    
    logger.info("🚀 FCM task started for user=%s restaurant=%s", user_id, restaurant_id)
    
    set_schema(restaurant_id)

    try:
        tokens = list(
            DeviceToken.objects
            .filter(user_id=user_id, is_active=True)
            .values_list("fcm_token", flat=True)
        )

        if not tokens:
            logger.info("📭 No active tokens for user %s", user_id)
            return

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            tokens=tokens,
        )

        response = messaging.send_each_for_multicast(message)

        logger.info(
            "📨 Push sent | user=%s success=%s failed=%s",
            user_id,
            response.success_count,
            response.failure_count,
        )

        for idx, resp in enumerate(response.responses):
            if not resp.success:
                DeviceToken.objects.filter(
                    fcm_token=tokens[idx]
                ).update(is_active=False)

    finally:
        reset_schema()



# Restaurent admin brodcaste message to all the user

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_restaurant_broadcast_notification_task(
    self,
    *,
    restaurant_id: str,
    title: str,
    body: str,
    role: str | None = None,
):

    logger.info(
        "🚀 Broadcast FCM task started | restaurant=%s role=%s",
        restaurant_id,
        role,
    )

    set_schema(restaurant_id)

    try:

        queryset = DeviceToken.objects.filter(
            restaurant_id=restaurant_id,
            is_active=True
        )

        if role:
            queryset = queryset.filter(role=role)

        tokens = list(
            queryset.values_list("fcm_token", flat=True)
        )

        if not tokens:
            logger.info(
                "📭 No tokens found for restaurant %s",
                restaurant_id
            )
            return

        # Firebase allows max 500 tokens per request
        for i in range(0, len(tokens), 500):

            batch = tokens[i:i + 500]

            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                tokens=batch,
            )

            response = messaging.send_each_for_multicast(message)

            logger.info(
                "📨 Broadcast sent | restaurant=%s success=%s failed=%s",
                restaurant_id,
                response.success_count,
                response.failure_count,
            )

            # deactivate invalid tokens
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    DeviceToken.objects.filter(
                        fcm_token=batch[idx]
                    ).update(is_active=False)

    finally:
        reset_schema()