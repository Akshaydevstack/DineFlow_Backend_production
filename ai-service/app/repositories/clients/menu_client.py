import httpx
import json
from app.core import config
from app.repositories.db.redis import redis_client

async def fetch_menu_dishes(restaurant_id: str, user_id: str = None, user_role: str = None) -> list:
    cache_key = f"menu_dishes:{restaurant_id}"

    # Check cache first
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis read error: {e}")

    # Fetch from menu service
    url = f"{config.MENU_SERVICE_URL}/api/menu/internal/ai/dishes/list/"
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
