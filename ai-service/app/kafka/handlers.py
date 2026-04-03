from loguru import logger
from app.db.ingest import (ingest_menu,
                           ingest_order_history,
                           update_order_status,
                           ingest_restaurants,
                           ingest_tables,
                           ingest_user_profile,
                           update_table_session_status)
from app.db.pgvector_client import (
    get_dish_version,
    update_dish_version,
    mark_dish_unavailable,
)

# --------------------------------------------------
# Menu event handler
# --------------------------------------------------


def handle_dish_event(event: dict, topic: str):
    restaurant_id = event.get("restaurant_id")
    dish_id = event.get("dish_id")
    menu_version = event.get("menu_version", "v0")

    incoming_version = int(menu_version.lstrip("v"))

    # 1. VERSION GUARD
    current_version = get_dish_version(dish_id, restaurant_id)
    if current_version is not None:
        if incoming_version <= current_version:
            logger.info(
                f"⏭️ Skipping stale event | dish={dish_id} | v{incoming_version} <= v{current_version}")
            return

    # 2. CREATE / UPDATE Logic
    if topic in ("menu.item.created", "menu.item.updated"):
        # Compile tags dynamically based on boolean fields
        tags = ["vegetarian"] if event.get("is_veg") else ["non-vegetarian"]
        if event.get("is_spicy"):
            tags.append("spicy")
        if event.get("is_popular"):
            tags.append("popular")
        if event.get("is_trending"):
            tags.append("trending")
        if event.get("is_quick_bites"):
            tags.append("quick bites")

        dish = {
            "id":             dish_id,
            "name":           event.get("name"),
            "description":    event.get("description", ""),
            "category":       event.get("category_name", ""),
            "category_id":    event.get("category_id", ""),
            "price":          float(event.get("price", 0)),
            "original_price": float(event.get("original_price", 0)) if event.get("original_price") else None,
            "available":      event.get("is_available", True),
            "prep_time":      event.get("prep_time"),
            "tags":           tags,
            "average_rating": float(event.get("average_rating", 0.0)),
            "review_count":   int(event.get("review_count", 0)),
            "total_orders":   int(event.get("total_orders", 0)),
            "priority":       int(event.get("priority", 0)),
            "image_url":      event.get("image_url", ""),
            "occurred_at":    event.get("occurred_at"),
            "version":        incoming_version,
        }

        ingest_menu(dishes=[dish], restaurant_id=restaurant_id)
        update_dish_version(dish_id, restaurant_id, incoming_version)
        logger.info(f"✅ Dish synced | {dish_id} | v{incoming_version}")

    # 3. DELETE Logic (Soft Delete)
    elif topic == "menu.item.deleted":
        mark_dish_unavailable(dish_id, restaurant_id, incoming_version)
        update_dish_version(dish_id, restaurant_id, incoming_version)
        logger.info(f"🗑️ Dish marked unavailable | {dish_id}")

# --------------------------------------------------
# Order event handler (Full Order Creation)
# --------------------------------------------------

def handle_order_event(event: dict, topic: str):
    """
    Catches the orders.placed event and prepares it for pgvector insertion.
    """
    restaurant_id = event.get("restaurant_id")
    user_id = event.get("user_id")

    # Map the exact fields from your Kafka payload
    order = {
        "order_id": event.get("order_id"),
        "date": event.get("created_at"),
        "status": event.get("status", "CREATED"),
        
        # Financials
        "total": event.get("total", "0.00"),
        "subtotal": event.get("subtotal", "0.00"),
        "tax": event.get("tax", "0.00"),
        "discount": event.get("discount", "0"),
        "currency": event.get("currency", "INR"),
        "payment_status": event.get("payment_status", "PENDING"),
        
        # Table & Location
        "table_number": event.get("table_number"),
        "table_public_id": event.get("table_public_id"),
        "zone_name": event.get("zone_name"),
        "zone_public_id": event.get("zone_public_id"),
        
        # Specifics
        "special_request": event.get("special_request", ""),
        "order_by": event.get("order_by", "customer"),
        
        # Items (passed exactly as received from Kafka)
        "items": event.get("items", [])
    }

    ingest_order_history(
        orders=[order],
        user_id=user_id,
        restaurant_id=restaurant_id
    )
    logger.info(f"✅ Order history created in vector DB | {order['order_id']}")


# --------------------------------------------------
# Order Status Update Handler (Cancellations & Kitchen)
# --------------------------------------------------

def handle_order_status_update(event: dict, topic: str):
    order_id = event.get("order_id")
    restaurant_id = event.get("restaurant_id")

    # Extract status based on topic or payload
    if topic == "orders.cancelled":
        status = "CANCELLED"
    else:
        # Fallback to event_type if status isn't explicitly passed
        status = event.get("status") or event.get("event_type")

    if not order_id or not status:
        logger.warning(f"⚠️ Missing order_id or status in event: {topic}")
        return

    # Update just the status in the vector DB / history
    update_order_status(
        order_id=order_id,
        restaurant_id=restaurant_id,
        status=status
    )
    logger.info(f"🔄 Order status updated | {order_id} -> {status}")


# --------------------------------------------------
# Restaurant Event Handler
# --------------------------------------------------

def handle_restaurant_event(event: dict, topic: str):
    public_id = event.get("public_id")
    name = event.get("name")

    if not public_id:
        logger.warning(f"⚠️ Missing public_id in restaurant event: {topic}")
        return

    # Our ingest_restaurants function expects a list of dictionaries.
    # We just wrap the single Kafka event dictionary in a list.
    ingest_restaurants([event])

    action = "created" if "created" in topic else "updated"
    logger.info(f"✅ Restaurant profile {action} | {public_id} ({name})")


# --------------------------------------------------
# Table Handlers
# --------------------------------------------------

def handle_table_upsert(event: dict, topic: str):
    table_id = event.get("table_public_id")
    if not table_id:
        logger.warning(f"⚠️ Missing table_public_id in event: {topic}")
        return

    ingest_tables([event])
    logger.info(f"✅ Table profile upserted | {table_id}")


def handle_table_session(event: dict, topic: str):
    table_id = event.get("table_public_id")
    restaurant_id = event.get("restaurant_id")

    if not table_id or not restaurant_id:
        logger.warning(
            f"⚠️ Missing table or restaurant ID in session event: {topic}")
        return

    # Determine state based on the topic
    if topic == "table.session.started":
        is_occupied = True
        user_id = event.get("user_id")
    elif topic == "table.session.closed":
        is_occupied = False
        user_id = None
    else:
        return

    update_table_session_status(table_id, restaurant_id, is_occupied, user_id)


# --------------------------------------------------
# User Event Handler (NEW)
# --------------------------------------------------

def handle_user_event(event: dict, topic: str):
    """
    Catches both user.created and user.updated topics.
    Passes the payload to the ingestion script, which UPSERTS the database.
    """
    user_id = event.get("user_id")
    email = event.get("email")

    if not user_id:
        logger.warning(f"⚠️ Missing user_id in event: {topic}")
        return

    # Ingests and UPSERTS the database automatically
    ingest_user_profile(event)

    action = "created" if "created" in topic else "updated"
    logger.info(f"👤 User profile {action} | {user_id} ({email})")
