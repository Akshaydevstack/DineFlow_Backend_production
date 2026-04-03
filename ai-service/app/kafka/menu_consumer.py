import json
from loguru import logger
import signal

from confluent_kafka import Consumer
import os

from .handlers import (handle_dish_event, handle_order_event, handle_order_status_update,
                       handle_restaurant_event, handle_table_upsert, handle_table_session, handle_user_event)

from .dlq_producer import send_to_dlq
from app.db.pgvector_client import setup_vector_tables

# --------------------------------------------------
# Config
# --------------------------------------------------
CONSUMER_NAME = "ai-service-consumer"
DLQ_TOPIC = "ai.service.dlq"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# ✅ Added new order and kitchen topics
VALID_TOPICS = {
    "menu.item.created",
    "menu.item.updated",
    "menu.item.deleted",
    "orders.placed",
    "orders.cancelled",
    "kitchen.ticket.created",
    "kitchen.ticket.accepted",
    "kitchen.ticket.preparing",
    "kitchen.ticket.ready",
    "kitchen.ticket.cancelled",
    "restaurant.created",  # NEW
    "restaurant.updated",   # NEW
    "restaurant.table.upsert",  # NEW
    "table.session.started",   # NEW
    "table.session.closed",    # NEW
    "user.created",
    "user.updated"

}

# ✅ Mapped new topics to the status update handler
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
    "restaurant.created":       handle_restaurant_event,  # NEW
    "restaurant.updated":       handle_restaurant_event,  # NEW
    "restaurant.table.upsert":  handle_table_upsert,
    "table.session.started":    handle_table_session,
    "table.session.closed":     handle_table_session,
    "user.created":             handle_user_event,  # 👈 MAPS HERE
    "user.updated":             handle_user_event,  # 👈 AND HERE
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
# Main consumer loop
# --------------------------------------------------


def consume_events():

    # Create tables FIRST before anything else
    setup_vector_tables()

    # Create consumer INSIDE function — not at module level
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id":          CONSUMER_NAME,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })

    # Subscribe INSIDE function — not at module level
    consumer.subscribe(list(VALID_TOPICS))

    logger.info(
        f"✅ AI Service Kafka consumer started — listening to {len(VALID_TOPICS)} topics")

    try:
        while running:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue

            try:
                event = json.loads(msg.value())
                topic = msg.topic()

                if topic not in VALID_TOPICS:
                    logger.warning(f"⚠️ Unknown topic: {topic}")
                    consumer.commit(msg)
                    continue

                handler = TOPIC_HANDLERS[topic]
                handler(event, topic)

                # Commit ONLY after success
                consumer.commit(msg)

            # Non-retriable → DLQ
            except (KeyError, ValueError) as e:
                logger.warning(
                    f"❌ Non-retriable ai-service event | "
                    f"topic={msg.topic()} | error={e} | payload={msg.value()}"
                )
                send_to_dlq(
                    topic=msg.topic(),
                    event=event,
                    error=e,
                    consumer=CONSUMER_NAME,
                    dlq_topic=DLQ_TOPIC,
                    key=event.get("dish_id") or event.get("order_id"),
                )
                consumer.commit(msg)

            # Retriable → don't commit
            except Exception:
                logger.exception(
                    "🔥 AI service consumer failed — retrying via Kafka offset"
                )
                continue

    finally:
        logger.info("🛑 AI service Kafka consumer shutting down")
        consumer.close()
