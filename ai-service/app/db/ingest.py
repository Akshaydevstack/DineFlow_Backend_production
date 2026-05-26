import json
from datetime import datetime
from sentence_transformers import SentenceTransformer
from loguru import logger

from .pgvector_client import (setup_vector_tables,
                              insert_menu_item,
                              insert_order_history,
                              get_order_metadata,
                              update_order_record,
                              insert_restaurant_info,
                              insert_table_info, 
                              get_table_metadata, 
                              update_table_record,
                              insert_user_info)

embedder = SentenceTransformer("/app/models/all-MiniLM-L6-v2")



def build_dish_text(dish: dict) -> str:
    parts = [
        f"Dish: {dish.get('name', '')}",
        f"Description: {dish.get('description', '')}",
        f"Category: {dish.get('category', '')}",
        "Vegetarian" if "vegetarian" in dish.get("tags", []) else "Non-Vegetarian",
        f"Price: ₹{dish.get('price', '')}",
    ]
    
    # Add semantic context if item is discounted
    if dish.get("original_price") and dish.get("original_price") > dish.get("price", 0):
        parts.append(f"Original Price: ₹{dish.get('original_price')} (Currently Discounted)")
        
    parts.append(f"Tags: {', '.join(dish.get('tags', []))}")
    
    if dish.get("prep_time"):
        parts.append(f"Prep time: {dish.get('prep_time')} mins")
        
    # Add semantic context for ratings
    if dish.get("average_rating", 0) > 0:
        parts.append(f"Rating: {dish.get('average_rating')} stars ({dish.get('review_count', 0)} reviews)")
        
    if dish.get("total_orders", 0) > 0:
        parts.append(f"Ordered {dish.get('total_orders')} times")

    # ✅ Added explicit semantic availability
    parts.append("Currently Available" if dish.get("available") else "Currently Unavailable (Sold Out)")

    parts.append(f"Last Updated: {dish.get('occurred_at', '')}")
    
    return " | ".join(filter(None, parts))


def ingest_menu(dishes: list, restaurant_id: str):
    setup_vector_tables()
    for dish in dishes:
        text = build_dish_text(dish)
        embedding = embedder.encode(text).tolist()

        metadata = {
            "name": dish.get("name"),
            "description": dish.get("description", ""),
            "price": dish.get("price"),
            "original_price": dish.get("original_price"),
            "category": dish.get("category", ""),
            "category_id": dish.get("category_id", ""), 
            "available": dish.get("available", True),
            "tags": dish.get("tags", []),
            "prep_time": dish.get("prep_time"),
            "average_rating": dish.get("average_rating"),
            "review_count": dish.get("review_count"),
            "total_orders": dish.get("total_orders"),
            "priority": dish.get("priority"),
            "image_url": dish.get("image_url", ""),
            "occurred_at": dish.get("occurred_at"),
            "version": dish.get("version")
        }

        insert_menu_item(
            dish_id=dish["id"],
            restaurant_id=restaurant_id,
            content=text,
            embedding=embedding,
            metadata=json.dumps(metadata)
        )


def build_order_text(order: dict) -> str:
    """Creates a semantic string representing a past order for the AI to search."""
    
    # Safely extract items using 'name' or 'dish_name'
    items = ", ".join([
        f"{i.get('name', i.get('dish_name', 'Item'))} x{i.get('quantity', 1)}" 
        for i in order.get("items", [])
    ])
    
    parts = [
        f"Order Date: {order.get('date')}",
        f"Items Ordered: {items}",
        f"Total: ₹{order.get('total')}",
        f"Status: {order.get('status')}",
        f"Payment: {order.get('payment_status')}"
    ]
    
    if order.get("special_request"):
        parts.append(f"Special Request: {order.get('special_request')}")
    if order.get("table_number"):
        parts.append(f"Table: {order.get('table_number')} ({order.get('zone_name', 'General')})")
        
    return " | ".join(parts)


def ingest_order_history(orders: list, user_id: str, restaurant_id: str):
    """Saves the fully enriched order data to pgvector."""
    for order in orders:
        text = build_order_text(order)
        embedding = embedder.encode(text).tolist()

        insert_order_history(
            user_id=user_id,
            restaurant_id=restaurant_id,
            content=text,
            embedding=embedding,
            metadata=order  # 👈 Pass the entire rich dictionary straight into the JSONB column!
        )



def update_order_status(order_id: str, restaurant_id: str, status: str):
    """
    Fetches the existing order, updates the status, re-generates the text 
    and vector embedding, and saves it back to the database.
    """
    # 1. Fetch the existing order metadata from Postgres
    existing_metadata = get_order_metadata(order_id, restaurant_id)

    if not existing_metadata:
        logger.warning(
            f"⚠️ Cannot update status: Order {order_id} not found in Vector DB.")
        return

    # ✅ ADDED: Idempotency check to prevent duplicate DB writes and embedding generation
    if existing_metadata.get("status") == status:
        logger.info(
            f"⏭️ Skipping update | Order {order_id} is already '{status}'")
        return

    # 2. Update the status in the metadata
    existing_metadata["status"] = status

    # 3. Re-build the text string using the existing order data
    # (Since your metadata contains 'items', 'total', 'date', it perfectly matches what build_order_text needs)
    new_text = build_order_text(existing_metadata)

    # 4. Generate the new embedding
    new_embedding = embedder.encode(new_text).tolist()

    # 5. Update the record in the database
    update_order_record(
        order_id=order_id,
        restaurant_id=restaurant_id,
        content=new_text,
        embedding=new_embedding,
        metadata=json.dumps(existing_metadata)
    )

    logger.info(
        f"🔄 Vector DB updated | Order {order_id} text and embedding synced with status: {status}")




def build_restaurant_text(rest: dict) -> str:
    parts = [
        f"Restaurant: {rest.get('name')}",
        f"Location: {rest.get('address')}, {rest.get('city')}, {rest.get('state')} {rest.get('pincode')}",
        f"Contact: Phone {rest.get('phone')}, Email {rest.get('email')}",
        f"Hours: {rest.get('opening_time')} to {rest.get('closing_time')}",
        "Currently Open" if rest.get("is_open") else "Currently Closed"
    ]
    # Add zones only if they exist in the payload (Kafka event won't have them yet)
    if rest.get('zones'):
        parts.append(f"Zones available: {', '.join(rest.get('zones'))}")
        
    return " | ".join(filter(None, parts))



def ingest_restaurants(restaurants: list):
    
    setup_vector_tables() # Ensures tables exist
    
    for rest in restaurants:
        text = build_restaurant_text(rest)
        embedding = embedder.encode(text).tolist()

        metadata = {
            "name": rest.get("name"),
            "slug": rest.get("slug"),
            "city": rest.get("city"),
            "is_active": rest.get("is_active", True),
            "is_open": rest.get("is_open", True),
            "zones": rest.get("zones", [])
        }

        insert_restaurant_info(
            public_id=rest["public_id"],
            content=text,
            embedding=embedding,
            metadata=metadata
        )


# --------------------------------------------------
# Table & Session Ingestion
# --------------------------------------------------

def build_table_text(table: dict) -> str:
    """Creates a semantic string representing a specific table."""
    status = "Occupied" if table.get('is_occupied') else "Available"
    
    parts = [
        f"Table Number: {table.get('table_number')}",
        f"Restaurant: {table.get('restaurant_name')}",
        f"Zone: {table.get('zone_name', 'General')}",
        f"Table Type: {table.get('table_type')}",
        f"Current Status: {status}"
    ]
    return " | ".join(filter(None, parts))


def ingest_tables(tables: list):
    """Handles the restaurant.table.upsert event."""
    setup_vector_tables()
    for table in tables:
        # Default to available if not specified
        table['is_occupied'] = table.get('is_occupied', False)
        
        text = build_table_text(table)
        embedding = embedder.encode(text).tolist()

        metadata = {
            "table_number": table.get("table_number"),
            "restaurant_name": table.get("restaurant_name"),
            "zone_name": table.get("zone_name"),
            "table_type": table.get("table_type"),
            "is_active": table.get("is_active", True),
            "is_occupied": table["is_occupied"],
            "current_user_id": table.get("current_user_id") # None if empty
        }

        insert_table_info(
            public_id=table["table_public_id"],
            restaurant_id=table["restaurant_id"],
            content=text,
            embedding=embedding,
            metadata=metadata
        )
    logger.info(f"✅ Ingested/Upserted {len(tables)} tables into vector DB.")


def update_table_session_status(table_public_id: str, restaurant_id: str, is_occupied: bool, user_id: str = None):
    """
    Fired by table.session.started and table.session.closed.
    Updates the table's embedding so the AI knows if it's currently occupied.
    """
    existing_metadata = get_table_metadata(table_public_id, restaurant_id)
    
    if not existing_metadata:
        logger.warning(f"⚠️ Cannot update session status: Table {table_public_id} not found in DB.")
        return

    # Idempotency Check
    if existing_metadata.get("is_occupied") == is_occupied:
        logger.info(f"⏭️ Skipping update | Table {table_public_id} is already occupied={is_occupied}")
        return

    existing_metadata["is_occupied"] = is_occupied
    existing_metadata["current_user_id"] = user_id if is_occupied else None

    # Re-build text and vector
    new_text = build_table_text(existing_metadata)
    new_embedding = embedder.encode(new_text).tolist()

    update_table_record(
        table_public_id=table_public_id,
        restaurant_id=restaurant_id,
        content=new_text,
        embedding=new_embedding,
        metadata=existing_metadata
    )
    
    state_str = "Occupied" if is_occupied else "Available"
    logger.info(f"🔄 Vector DB updated | Table {table_public_id} status changed to: {state_str}")






def build_user_text(user_payload: dict) -> str:
    """Creates a semantic string representing a user profile."""
    parts = [
        f"User Name: {user_payload.get('name', 'Guest')}",
        f"Email Address: {user_payload.get('email', 'Not provided')}",
        f"Role: {user_payload.get('role', 'Customer')}",
        f"Member since: {user_payload.get('created_at', '')}",
    ]
    return " | ".join(filter(None, parts))


def ingest_user_profile(payload: dict):
    """
    Handles the user.created Kafka event.
    Converts the Kafka payload into a vector and stores it.
    """
    setup_vector_tables() # Ensures tables exist
    
    text = build_user_text(payload)
    embedding = embedder.encode(text).tolist()

    metadata = {
        "user_id": payload.get("user_id"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "role": payload.get("role"),
        "restaurant_id": payload.get("restaurant_id"),
        "created_at": payload.get("created_at")
    }

    insert_user_info(
        user_id=payload["user_id"],
        content=text,
        embedding=embedding,
        metadata=metadata
    )
    logger.info(f"✅ Ingested user profile for {payload.get('email')} into vector DB.")