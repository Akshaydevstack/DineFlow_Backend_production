import httpx
import os

# CART_SERVICE_URL = os.getenv(
#     "CART_SERVICE_URL",
#     "http://cart-service.dineflow-dev.svc.cluster.local:8000"
# )

CART_SERVICE_URL = os.getenv(
    "CART_SERVICE_URL",
    "http://cart-service.dineflow-production.svc.cluster.local:8000"
)

DEFAULT_HEADERS = {
    "X-Internal-Call": "true"
}


async def tool_add_to_cart(user_id, restaurant_id, dish_id, quantity=1):
    url = f"{CART_SERVICE_URL}/api/cart/internal/ai/add/"

    headers = {
        **DEFAULT_HEADERS,
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.post(
            url,
            json={
                "dish_id": dish_id,
                "quantity": quantity
            },
            headers=headers
        )

    if res.status_code != 200:
        print("Add to cart error:", res.status_code, res.text)
        return {"error": "failed_to_add"}

    return res.json()


# --------------------------------------------------


async def tool_update_cart(user_id, restaurant_id, dish_id, quantity):
    url = f"{CART_SERVICE_URL}/api/cart/internal/ai/update/"

    headers = {
        **DEFAULT_HEADERS,
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.patch(
            url,
            json={
                "dish_id": dish_id,
                "quantity": quantity
            },
            headers=headers
        )

    if res.status_code != 200:
        print("Update cart error:", res.status_code, res.text)
        return {"error": "failed_to_update"}

    return res.json()


# --------------------------------------------------


async def tool_remove_from_cart(user_id, restaurant_id, dish_id):
    url = f"{CART_SERVICE_URL}/api/cart/internal/ai/remove/"

    headers = {
        **DEFAULT_HEADERS,
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.request(
            "DELETE",   # ⚠️ use request() because some servers ignore body in delete()
            url,
            json={"dish_id": dish_id},
            headers=headers
        )

    if res.status_code != 200:
        print("Remove item error:", res.status_code, res.text)
        return {"error": "failed_to_remove"}

    return res.json()


# --------------------------------------------------


async def tool_clear_cart(user_id, restaurant_id):
    url = f"{CART_SERVICE_URL}/api/cart/internal/ai/clear/"

    headers = {
        **DEFAULT_HEADERS,
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.delete(url, headers=headers)

    if res.status_code != 200:
        print("Clear cart error:", res.status_code, res.text)
        return {"error": "failed_to_clear"}

    return res.json()




async def tool_view_cart(user_id, restaurant_id):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{CART_SERVICE_URL}/api/cart/internal/ai/list-items/",
            headers={
                **DEFAULT_HEADERS,
                "X-User-Id": user_id,
                "X-Restaurant-Id": restaurant_id
            }
        )

    return res.json()