import json
import logging
import signal
from confluent_kafka import Consumer
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError
from restaurant.models import Table
from kafka.table_session_dlq_producer import send_to_table_session_dlq

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Config
# --------------------------------------------------
CONSUMER_NAME = "auth-table-session-consumer"
DLQ_TOPIC = "table.session.dlq"

VALID_TOPICS = {
    "table.session.started",
    "table.session.closed",
}

running = True


# --------------------------------------------------
# Graceful shutdown
# --------------------------------------------------
def shutdown(signum, frame):
    global running
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# --------------------------------------------------
# Kafka Consumer
# --------------------------------------------------
consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKER,
    "group.id": CONSUMER_NAME,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

consumer.subscribe(list(VALID_TOPICS))


# --------------------------------------------------
# Event Processor (IDEMPOTENT)
# --------------------------------------------------
def process_event(event: dict, topic: str):

    if topic not in VALID_TOPICS:
        raise ValueError(f"Unknown topic: {topic}")

    restaurant_id = event.get("restaurant_id")
    table_public_id = event.get("table_public_id")

    if not restaurant_id or not table_public_id:
        raise ValueError("Invalid payload")

    with transaction.atomic():

        table = Table.objects.select_for_update().filter(
            public_id=table_public_id,
            restaurant__public_id=restaurant_id,
        ).first()

        if not table:
            logger.warning(
                "Table not found in auth service",
                extra={
                    "restaurant_id": restaurant_id,
                    "table_public_id": table_public_id,
                },
            )
            return

        # --------------------------------------------
        # SESSION STARTED
        # --------------------------------------------
        if topic == "table.session.started":

            event_user_id = event.get("user_id")

            # Already occupied
            if table.is_occupied:

                # If same user → idempotent, safe to ignore
                if table.occupied_by_user_id == event_user_id:
                    logger.info(
                        f"⏭️ Duplicate session start ignored | table={table_public_id}"
                    )
                    return

                # If different user → serious conflict
                logger.error(
                    f"⚠️ Table ownership conflict | table={table_public_id}"
                )
                return

            # Fresh occupancy
            table.is_occupied = True
            table.occupied_by_user_id = event_user_id

            table.save(update_fields=["is_occupied", "occupied_by_user_id"])

            logger.info(
                f"🪑 Table marked occupied | table={table_public_id}"
            )

        # --------------------------------------------
        # SESSION CLOSED
        # --------------------------------------------
        elif topic == "table.session.closed":

            # Already free → idempotent
            if not table.is_occupied:
                logger.info(
                    f"⏭️ Duplicate session close ignored | table={table_public_id}"
                )
                return

            table.is_occupied = False
            table.occupied_by_user_id = None  # 🔥 CLEAR OWNER

            table.save(update_fields=["is_occupied", "occupied_by_user_id"])

            logger.info(
                f"🟢 Table marked free | table={table_public_id}"
            )


# --------------------------------------------------
# Main Consumer Loop
# --------------------------------------------------
def consume_table_session_events():

    logger.info("🪑 Auth Table Session Kafka consumer started")

    try:
        while running:

            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(msg.error())
                continue

            try:
                event = json.loads(msg.value())
                topic = msg.topic()

                process_event(event, topic)

                # ✅ Commit only after success
                consumer.commit(msg)

            # ------------------------------------------
            # ❌ Non-retriable → DLQ
            # ------------------------------------------
            except (KeyError, ValidationError, ValueError) as e:

                logger.warning(
                    "❌ Non-retriable table-session event",
                    extra={
                        "error": str(e),
                        "topic": msg.topic(),
                        "payload": msg.value(),
                    },
                )

                send_to_table_session_dlq(
                    topic=msg.topic(),
                    event=event,
                    error=e,
                    consumer=CONSUMER_NAME,
                    dlq_topic=DLQ_TOPIC,
                    key=event.get("table_public_id"),
                )

                consumer.commit(msg)

            # ------------------------------------------
            # 🔁 Retriable → Kafka retry
            # ------------------------------------------
            except Exception:
                logger.exception(
                    "🔥 Table session consumer failed — retrying"
                )
                # No commit → Kafka will retry
                continue

    finally:
        logger.info("🛑 Auth table session consumer shutting down")
        consumer.close()
