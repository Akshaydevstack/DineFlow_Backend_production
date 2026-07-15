import httpx
import json
from app.core import config
from app.repositories.db.redis import redis_client

DEFAULT_HEADERS = {
    "X-Internal-Call": "true"
}


def _invalidate_cart_cache(user_id: str, restaurant_id: str):
    try:
        cache_key = f"user_cart:{user_id}:{restaurant_id}"
        redis_client.delete(cache_key)
    except Exception as e:
        print(f"Redis cache invalidation error (cart): {e}")


async def fetch_user_cart(user_id: str, restaurant_id: str) -> list:
    """Fetch user cart with short Redis caching (45 sec). Used by recommendations."""
    cache_key = f"user_cart:{user_id}:{restaurant_id}"

    # Cache Read
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis read error (cart): {e}")

    # API Call
    url = f"{config.CART_SERVICE_URL}/api/cart/internal/ai/items/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        **DEFAULT_HEADERS
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, headers=headers)
    except Exception as e:
        print(f"Cart API request failed: {e}")
        return []

    if res.status_code != 200:
        print("Cart API error:", res.status_code, res.text)
        return []

    data = res.json()
    cart_items = data if isinstance(data, list) else []

    # Cache Write
    try:
        redis_client.setex(cache_key, 45, json.dumps(cart_items))
    except Exception as e:
        print(f"Redis write error (cart): {e}")

    return cart_items


async def tool_view_cart(user_id: str, restaurant_id: str) -> dict:
    """View detailed user cart. Used by Agent tools."""
    url = f"{config.CART_SERVICE_URL}/api/cart/internal/ai/list-items/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        **DEFAULT_HEADERS
    }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(url, headers=headers)
        
    if res.status_code != 200:
        return {"error": "failed_to_view"}
    return res.json()


async def tool_add_to_cart(user_id: str, restaurant_id: str, dish_id: str, quantity: int = 1) -> dict:
    _invalidate_cart_cache(user_id, restaurant_id)
    url = f"{config.CART_SERVICE_URL}/api/cart/internal/ai/add/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        **DEFAULT_HEADERS
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.post(
            url,
            json={"dish_id": dish_id, "quantity": quantity},
            headers=headers
        )

    if res.status_code != 200:
        print("Add to cart error:", res.status_code, res.text)
        return {"error": "failed_to_add"}
    return res.json()


async def tool_update_cart(user_id: str, restaurant_id: str, dish_id: str, quantity: int) -> dict:
    _invalidate_cart_cache(user_id, restaurant_id)
    url = f"{config.CART_SERVICE_URL}/api/cart/internal/ai/update/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        **DEFAULT_HEADERS
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.patch(
            url,
            json={"dish_id": dish_id, "quantity": quantity},
            headers=headers
        )

    if res.status_code != 200:
        print("Update cart error:", res.status_code, res.text)
        return {"error": "failed_to_update"}
    return res.json()


async def tool_remove_from_cart(user_id: str, restaurant_id: str, dish_id: str) -> dict:
    _invalidate_cart_cache(user_id, restaurant_id)
    url = f"{config.CART_SERVICE_URL}/api/cart/internal/ai/remove/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        **DEFAULT_HEADERS
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.request(
            "DELETE",
            url,
            json={"dish_id": dish_id},
            headers=headers
        )

    if res.status_code != 200:
        print("Remove item error:", res.status_code, res.text)
        return {"error": "failed_to_remove"}
    return res.json()


async def tool_clear_cart(user_id: str, restaurant_id: str) -> dict:
    _invalidate_cart_cache(user_id, restaurant_id)
    url = f"{config.CART_SERVICE_URL}/api/cart/internal/ai/clear/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        **DEFAULT_HEADERS
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.delete(url, headers=headers)

    if res.status_code != 200:
        print("Clear cart error:", res.status_code, res.text)
        return {"error": "failed_to_clear"}
    return res.json()
