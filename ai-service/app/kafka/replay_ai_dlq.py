import json
import signal
import os
from loguru import logger
from confluent_kafka import Consumer

# Import your handlers
from .handlers import (
    handle_dish_event, handle_order_event, handle_order_status_update,
    handle_restaurant_event, handle_table_upsert, handle_table_session, handle_user_event
)

from app.db.pgvector_client import setup_vector_tables

# --------------------------------------------------
# Config
# --------------------------------------------------
REPLAY_CONSUMER_GROUP = "ai-service-dlq-replay-group"
DLQ_TOPIC = "ai.service.dlq"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "host.docker.internal:9092")

# Reuse the same topic mapping from your main consumer
TOPIC_HANDLERS = {
    "menu.item.created":        handle_dish_event,
    "menu.item.updated":        handle_dish_event,
    "menu.item.deleted":        handle_dish_event,
    "orders.placed":            handle_order_event,
    "orders.cancelled":         handle_order_status_update,
    "kitchen.ticket.created":   handle_order_status_update,
    "kitchen.ticket.accepted":  handle_order_status_update,
    "kitchen.ticket.preparing": handle_order_status_update,
    "kitchen.ticket.ready":     handle_order_status_update,
    "kitchen.ticket.cancelled": handle_order_status_update,
    "restaurant.created":       handle_restaurant_event,
    "restaurant.updated":       handle_restaurant_event,
    "restaurant.table.upsert":  handle_table_upsert,
    "table.session.started":    handle_table_session,
    "table.session.closed":     handle_table_session,
    "user.created":             handle_user_event,
    "user.updated":             handle_user_event,
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
# Main Replay Loop
# --------------------------------------------------
def replay_dlq_events():
    logger.info("🔁 AI Service DLQ replay started")

    # Ensure tables exist just in case
    setup_vector_tables()

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": REPLAY_CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })

    consumer.subscribe([DLQ_TOPIC])

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue

            try:
                # 1. Unpack the DLQ payload
                payload = json.loads(msg.value())
                
                original_topic = payload.get("original_topic")
                event = payload.get("event")
                retry_count = payload.get("retry_count", 0)

                if original_topic not in TOPIC_HANDLERS:
                    logger.warning(f"⚠️ Unknown original topic in DLQ: {original_topic}")
                    consumer.commit(msg)
                    continue

                # 2. Re-process the event
                handler = TOPIC_HANDLERS[original_topic]
                handler(event, original_topic)

                # 3. Commit only if successful
                consumer.commit(msg)
                logger.success(
                    f"✅ Successfully replayed DLQ event | "
                    f"topic={original_topic}, retry_count={retry_count}"
                )

            except Exception as e:
                logger.exception("❌ AI Service DLQ replay failed")
                logger.error(f"❌ Replay failed, message kept in DLQ: {e}")
                # ❗ DO NOT commit → message stays in the DLQ to be replayed again later

    finally:
        logger.warning("🛑 AI Service DLQ replay stopped")
        consumer.close()

if __name__ == "__main__":
    replay_dlq_events()