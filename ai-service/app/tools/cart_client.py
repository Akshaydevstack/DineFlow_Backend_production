import httpx
import os
import json
import redis

# CART_SERVICE_URL = os.getenv(
#     "CART_SERVICE_URL",
#     "http://cart-service.dineflow-dev.svc.cluster.local:8000"
# )

CART_SERVICE_URL = os.getenv(
    "CART_SERVICE_URL",
    "http://cart-service.dineflow-production.svc.cluster.local:8000"
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis.dineflow-production.svc.cluster.local"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)


async def fetch_user_cart(user_id: str, restaurant_id: str):
    cache_key = f"user_cart:{user_id}:{restaurant_id}"

    # ==========================
    # CACHE READ
    # ==========================
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis read error (cart): {e}")

    # ==========================
    # API CALL
    # ==========================
    url = f"{CART_SERVICE_URL}/api/cart/internal/ai/items/"

    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        "X-Internal-Call": "true"
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

    # ==========================
    # CACHE WRITE (SHORT TTL)
    # ==========================
    try:
        redis_client.setex(
            cache_key,
            45,  # 🔥 45 sec TTL (important)
            json.dumps(cart_items)
        )
    except Exception as e:
        print(f"Redis write error (cart): {e}")

    return cart_items