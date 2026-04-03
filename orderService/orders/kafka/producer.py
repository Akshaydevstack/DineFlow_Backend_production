import json
import logging
from confluent_kafka import Producer
from django.conf import settings

logger = logging.getLogger(__name__)

_producer = None



def get_producer():
    global _producer
    if _producer is None:
        conf = {
            "bootstrap.servers": settings.KAFKA_BROKER,
            "acks": "all",
            "retries": 3,
            "linger.ms": 10,
            "enable.idempotence": True,          
        }
        _producer = Producer(conf)
    return _producer



def _delivery_report(err, msg):
    if err is not None:
        logger.error(
            "Kafka delivery failed",
            extra={
                "topic": msg.topic(),
                "key": msg.key(),
                "error": str(err),
            },
        )



def serialize_order_items(order):
    return [
        {
            "dish_id": item.dish_id,
            # AI email tool looks for "name" or "dish_name"
            "name": item.dish_name, 
            "dish_name": item.dish_name,
            "quantity": item.quantity,
            "unit_price": str(item.unit_price),
            "total_price": str(item.total_price),
            "total": str(item.total_price), # AI email tool fallback
            "image" : item.image_url
        }
        for item in order.items.all()
    ]


def publish_order_placed(order):
    producer = get_producer()

    event = {
        "event_type": "ORDER_PLACED",
        "order_id": order.public_id,
        "user_id": order.user_id,
        "restaurant_id": order.restaurant_id,
        "status": order.status,
        
        # 🔹 Financials (Critical for AI Email Receipts)
        "subtotal": str(order.subtotal),
        "tax": str(order.tax),
        "discount": str(order.discount),
        "total": str(order.total),
        "currency": order.currency,

        # 🔹 Table & Location Info
        "table_number": order.table_number,
        "table_public_id": order.table_public_id,
        "zone_name": order.zone_name,
        "zone_public_id": order.zone_public_id,

        # 🔹 Order Specifics
        "special_request": order.special_request,
        "payment_status": order.payment_status,
        "order_by": order.order_by,
        
        # 🔹 Items and Timestamps
        "items": serialize_order_items(order), 
        "created_at": order.created_at.isoformat(),
    }

    producer.produce(
        topic="orders.placed",
        key=order.public_id,
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.flush()





def publish_order_cancelled(order):
    producer = get_producer()

    event = {
        "event_type": "ORDER_CANCELLED",
        "order_id": order.public_id,
        "user_id": order.user_id,
        "restaurant_id": order.restaurant_id,
        "cancelled_by": "CUSTOMER",
        "cancelled_at": order.updated_at.isoformat(),
    }

    producer.produce(
        topic="orders.cancelled",
        key=order.public_id,
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.poll(0)






def publish_session_started(session,user_id):
    producer = get_producer()

    event = {
        "event_type": "TABLE_SESSION_STARTED",
        "session_id": session.public_id,
        "session_version": session.session_version,
        "restaurant_id": session.restaurant_id,
        "table_public_id": session.table_public_id,
        "table_number": session.table_number,
        "zone_public_id": session.zone_public_id,
        "zone_name": session.zone_name,
        "status": session.status,
        "user_id": user_id,
        "started_at": session.started_at.isoformat(),
    }

    producer.produce(
        topic="table.session.started",
        key=session.table_public_id,
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.poll(0)





def publish_session_closed(session):
    producer = get_producer()

    event = {
        "event_type": "TABLE_SESSION_CLOSED",
        "session_id": session.public_id,
        "session_version": session.session_version,
        "restaurant_id": session.restaurant_id,
        "table_public_id": session.table_public_id,
        "status": session.status,
        "closed_at": session.closed_at.isoformat()
        if session.closed_at
        else None,
    }

    producer.produce(
        topic="table.session.closed",
        key=session.table_public_id,
        value=json.dumps(event),
        on_delivery=_delivery_report,
    )

    producer.poll(0)