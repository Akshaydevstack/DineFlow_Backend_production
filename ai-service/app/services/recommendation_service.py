import asyncio
from loguru import logger
from typing import Dict, Any

from app.repositories.db.dynamo import get_user_history, store_dish_view
from app.repositories.clients.cart_client import fetch_user_cart
from app.repositories.clients.order_client import fetch_user_orders
from app.repositories.clients.menu_client import fetch_menu_dishes
from app.services.recommendation_engine import get_ai_recommendations_sync


async def get_recommendations(user_id: str, restaurant_id: str) -> list:
    """Gets AI recommendations, falling back to top-rated items if no context signals exist."""
    views = await asyncio.to_thread(get_user_history, user_id)
    cart = await fetch_user_cart(user_id, restaurant_id)
    orders = await fetch_user_orders(user_id, restaurant_id)
    dishes = await fetch_menu_dishes(restaurant_id)

    if not dishes:
        return []

    # If no historical inputs exist, return top 10 rated dishes
    if not views and not cart and not orders:
        return sorted(
            dishes,
            key=lambda d: float(d.get("average_rating") or 0),
            reverse=True
        )[:10]

    try:
        return await asyncio.to_thread(
            get_ai_recommendations_sync,
            views, cart, orders, dishes,
            user_id=user_id,
            restaurant_id=restaurant_id
        )
    except Exception as e:
        logger.error(f"Recommendation error, falling back: {e}")
        return sorted(
            dishes,
            key=lambda d: float(d.get("average_rating") or 0),
            reverse=True
        )[:10]


async def track_dish_view(user_id: str, dish: Dict[str, Any], restaurant_id: str):
    """Tracks a dish view by storing it to DynamoDB."""
    await asyncio.to_thread(store_dish_view, user_id, dish, restaurant_id)
