import httpx
import json
import os
import redis

# MENU_SERVICE_URL = os.getenv(
#     "MENU_SERVICE_URL",
#     "http://menu-service.dineflow-dev.svc.cluster.local:8000"
# )

# redis_client = redis.Redis(
#     host=os.getenv("REDIS_HOST", "localhost"),
#     port=int(os.getenv("REDIS_PORT", 6379)),
#     db=0,
#     decode_responses=True
# )


MENU_SERVICE_URL = os.getenv(
    "MENU_SERVICE_URL",
    "http://menu-service.dineflow-production.svc.cluster.local:8000"
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis.dineflow-production.svc.cluster.local"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)


async def fetch_menu_dishes(restaurant_id: str, user_id: str = None, user_role: str = None):
    cache_key = f"menu_dishes:{restaurant_id}"

    # Check cache first
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis read error: {e}")

    # Fetch from menu service
    url = f"{MENU_SERVICE_URL}/api/menu/internal/ai/dishes/list/"
    headers = {"X-Restaurant-Id": restaurant_id, "X-Internal-Call": "true"}

    if user_id:
        headers["X-User-Id"] = user_id
    if user_role:
        headers["X-User-Role"] = user_role

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(url, headers=headers)

    if res.status_code != 200:
        print("Menu AI API Error:", res.status_code, res.text)
        return []

    data = res.json()

    if isinstance(data, list):
        dishes = data
    elif isinstance(data, dict) and "results" in data:
        dishes = data["results"]
    else:
        print("Unexpected menu response:", data)
        return []

    # Cache for 10 minutes (menu changes rarely)
    try:
        redis_client.setex(cache_key, 600, json.dumps(dishes))
    except Exception as e:
        print(f"Redis write error: {e}")

    return dishes