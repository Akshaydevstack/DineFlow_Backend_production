import asyncio
import concurrent.futures
from langchain_core.tools import tool

from app.tools.recommendation_engine import get_ai_recommendations_sync
from app.tools.dynamo_tools import get_user_history
from app.tools.menu_client import fetch_menu_dishes
from app.tools.cart_client import fetch_user_cart
from app.tools.order_client import fetch_user_orders

def _run_safe(coro):
    """Safely execute async functions within LangGraph."""
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)

@tool
def tool_get_personalized_recommendations(user_id: str, restaurant_id: str) -> str:
    """
    Fetches personalized dish recommendations based on user history, cart, and orders.
    Use this for queries like "What should I eat?", "What's good?", or "What do you recommend?"
    """
    try:
        # Fetch data safely using our threadpool workaround
        views = get_user_history(user_id)
        cart = _run_safe(fetch_user_cart(user_id, restaurant_id))
        orders = _run_safe(fetch_user_orders(user_id, restaurant_id))
        dishes = _run_safe(fetch_menu_dishes(restaurant_id))
        
        recs = get_ai_recommendations_sync(
            views, cart, orders, dishes, 
            user_id=user_id, 
            restaurant_id=restaurant_id
        )

        if not recs:
            return "I don't have enough history to make a personal recommendation yet, but our menu has great options!"

        lines = []
        for meta in recs:
            # ✅ FIX 1: Extract the first image from the 'images' array returned by the API
            images_array = meta.get("images", [])
            image_url = images_array[0] if isinstance(images_array, list) and len(images_array) > 0 else ""
            
            prep_str = f"Prep: {meta.get('prep_time')} mins" if meta.get("prep_time") else "Prep: N/A"
            dish_id = meta.get("public_id", meta.get("dish_id", "Unknown"))
            available = meta.get("is_available", meta.get("available", True))
            
            # The inline properties separated by |
            dish_line = (
                f"- {meta.get('name', 'Unknown')} | "
                f"₹{meta.get('price', 'N/A')} | "
                f"{'✅ Available' if available else '❌ Unavailable'} | "
                f"{prep_str} | "
                f"dish_id: {dish_id} | "
                f"image: {image_url}"
            )
            
            # Description
            description = meta.get("description", "").strip()
            if description:
                dish_line += f"\n  Description: {description}"
                
            # ✅ FIX 2: Convert Django API boolean flags into a comma-separated tags string
            tags_list = []
            if meta.get("is_veg"): tags_list.append("Vegetarian")
            elif meta.get("is_veg") is False: tags_list.append("Non-Vegetarian")
            if meta.get("is_spicy"): tags_list.append("Spicy")
            if meta.get("is_popular"): tags_list.append("Popular")
            if meta.get("is_trending"): tags_list.append("Trending")
            if meta.get("is_quick_bites"): tags_list.append("Quick Bites")
            
            tags = ", ".join(tags_list)
            
            # Handle allergens if they ever get added to the serializer
            allergens_data = meta.get("allergens", [])
            allergens = ", ".join(allergens_data) if isinstance(allergens_data, list) else str(allergens_data)
            
            dish_line += f"\n  Tags: {tags} | Allergens: {allergens}"
            
            lines.append(dish_line)
        
        return "\n".join(lines)

    except Exception as e:
        return f"I couldn't pull your recommendations right now. System Error: {str(e)}"