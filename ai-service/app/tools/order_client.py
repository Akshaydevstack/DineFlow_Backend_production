import httpx
import json
import os
import redis

# ORDER_SERVICE_URL = os.getenv(
#     "ORDER_SERVICE_URL",
#     "http://order-service.dineflow-dev.svc.cluster.local:8000"
# )

# redis_client = redis.Redis(
#     host=os.getenv("REDIS_HOST", "localhost"),
#     port=int(os.getenv("REDIS_PORT", 6379)),
#     db=0,
#     decode_responses=True
# )

ORDER_SERVICE_URL = os.getenv(
    "ORDERS_SERVICE_URL",
    "http://order-service.dineflow-production.svc.cluster.local:8000"
)


redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis.dineflow-production.svc.cluster.local"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)


async def fetch_user_orders(user_id: str, restaurant_id: str):
    cache_key = f"user_orders:{user_id}:{restaurant_id}"

    # Check cache first
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis read error: {e}")

    # Fetch from order service
    url = f"{ORDER_SERVICE_URL}/api/order/internal/ai/orders/"
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        "X-Internal-Call": "true"
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(url, headers=headers)

    if res.status_code != 200:
        print("Order API error:", res.status_code, res.text)
        return []

    data = res.json()
    orders = data if isinstance(data, list) else []

    # Cache for 3 minutes
    try:
        redis_client.setex(cache_key, 180, json.dumps(orders))
    except Exception as e:
        print(f"Redis write error: {e}")

    return orders