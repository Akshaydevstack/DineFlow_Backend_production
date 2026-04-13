import os
import json
import httpx
import uuid
import asyncio
import concurrent.futures
from langchain_core.tools import tool
from app.agents.core.memory import get_session

from app.agents.tools.cart_client import (
    tool_view_cart as _view,
    tool_clear_cart as _clear,
)

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

# ⚡ THE FIX: Transient memory cache for lightning-fast location handoff
USER_LOCATION_CACHE = {}

def set_user_location(user_id: str, lat: float, lon: float):
    if lat is not None and lon is not None:
        USER_LOCATION_CACHE[user_id] = {"lat": lat, "lon": lon}


@tool
def place_order(user_id: str, restaurant_id: str, table_public_id: str) -> str:
    """
    Place an order using whatever is currently in the user's cart.
    IMPORTANT: Always call cart_view first and show summary to user.
    Only call this after explicit confirmation ("yes", "confirm", "go ahead").
    """
    # ⚡ 1. Pull location instantly from RAM instead of the database!
    loc = USER_LOCATION_CACHE.get(user_id, {})
    user_lat = loc.get("lat")
    user_lon = loc.get("lon")

    if user_lat is None or user_lon is None:
        return "Order failed: I could not determine your location. Please ensure location services are enabled on your device so I can verify you are at the restaurant."

    # 2. Fetch cart
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

    # 3. Prepare request
    idempotency_key = str(uuid.uuid4())
    payload = {
        "table_public_id": table_public_id,
        "user_latitude": user_lat,
        "user_longitude": user_lon,
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

    # 4. Call Order API
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
        # Parse DRF Validation Errors nicely for the AI
        try:
            err_data = e.response.json()
            if "location" in err_data:
                return f"Order failed: {err_data['location'][0]}"
            
            first_key = list(err_data.keys())[0]
            first_err = err_data[first_key]
            if isinstance(first_err, list):
                return f"Order failed: {first_err[0]}"
            return f"Order failed: {first_err}"
        except Exception:
            return f"Order failed (HTTP {e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Order failed: {str(e)}"

    # 5. Clear cart after success
    _run_safe(_clear(user_id, restaurant_id))
    
    # 6. Clear transient location memory to keep RAM clean
    USER_LOCATION_CACHE.pop(user_id, None)

    # 7. Format response
    order = order_data.get("order", order_data)

    return json.dumps({
        "order_id": order.get("order_id", order.get("public_id")),
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