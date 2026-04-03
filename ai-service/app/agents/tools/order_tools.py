import os
import json
import httpx
import uuid
import asyncio
import concurrent.futures
from langchain_core.tools import tool

from app.agents.tools.cart_client import (
    tool_view_cart as _view,
    tool_clear_cart as _clear,
)



# ORDERS_SERVICE_URL = os.getenv(
#     "ORDERS_SERVICE_URL",
#     "http://order-service.dineflow-dev:8000"
# )


ORDERS_SERVICE_URL = os.getenv(
    "ORDERS_SERVICE_URL",
    "http://order-service.dineflow-production.svc.cluster.local:8000"
)


def _run_safe(coro):
    """Safely execute async functions within LangGraph."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)





@tool
def place_order(user_id: str, restaurant_id: str, table_public_id: str) -> str:
    """
    Place an order using whatever is currently in the user's cart.
    IMPORTANT: Always call cart_view first and show summary to user.
    Only call this after explicit confirmation ("yes", "confirm", "go ahead").
    """
    # 1. Fetch cart
    cart = _run_safe(_view(user_id, restaurant_id))

    if isinstance(cart, dict) and "error" in cart:
        return f"Could not fetch cart: {cart.get('detail', '')}"

    if isinstance(cart, list):
        items = cart
    elif isinstance(cart, dict):
        items = cart.get("items", [])
    else:
        items = []

    if not items:
        return "Cart is empty — nothing to order."

    # 2. Prepare request
    idempotency_key = str(uuid.uuid4())
    payload = {
        "table_public_id": table_public_id,
        "items": [
            {
                "dish_id": item.get("dish_id"),
                "quantity": item.get("quantity"),
            }
            for item in items if item.get("dish_id")
        ],
    }

    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
        "X-Idempotency-Key": idempotency_key,
    }

    # 3. Call Order API
    try:
        response = httpx.post(
            f"{ORDERS_SERVICE_URL}/api/order/internal/ai/create-order/",
            json=payload,
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        order_data = response.json()

    except httpx.HTTPStatusError as e:
        return f"Order failed (HTTP {e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Order failed: {str(e)}"

    # 4. Clear cart after success
    _run_safe(_clear(user_id, restaurant_id))

    # 5. Format response
    order = order_data.get("order", order_data)

    return json.dumps({
        "order_id": order.get("order_id"),
        "status":   order.get("status"),
        "total":    order.get("total"),
        "items":    order.get("items"),
    }, indent=2)





@tool
def cancel_order(user_id: str, restaurant_id: str, public_id: str) -> str:
    """
    Cancel an existing active order.
    Use this when a user explicitly asks to cancel their order.
    You must provide the order's public_id (e.g., 'ORD-1234ABCD').
    """
    headers = {
        "X-User-Id": user_id,
        "X-Restaurant-Id": restaurant_id,
    }

    try:
        # Assuming the base path includes /api/order/ based on the place_order tool
        url = f"{ORDERS_SERVICE_URL}/api/order/internal/ai/{public_id}/cancel-order/"
        
        response = httpx.post(
            url,
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        order_data = response.json()

    except httpx.HTTPStatusError as e:
        # Attempt to parse the {"detail": "..."} response from Django
        try:
            error_detail = e.response.json().get("detail", e.response.text)
        except Exception:
            error_detail = e.response.text
            
        return f"Order cancellation failed (HTTP {e.response.status_code}): {error_detail}"
    except Exception as e:
        return f"Order cancellation failed: {str(e)}"

    # Format the successful response
    order = order_data.get("order", order_data)
    
    return json.dumps({
        "message": "Order cancelled successfully.",
        "order_id": order.get("public_id", public_id),
        "status": order.get("status", "CANCELLED"),
    }, indent=2)