import json
import asyncio
import concurrent.futures
from langchain_core.tools import tool

from app.agents.tools.cart_client import (
    tool_add_to_cart      as _add,
    tool_update_cart      as _update,
    tool_remove_from_cart as _remove,
    tool_clear_cart       as _clear,
    tool_view_cart        as _view,
)


def _run_safe(coro):
    """
    Run an async client coroutine safely from a sync LangChain tool.
    Prevents 'Event loop already running' crashes in FastAPI/LangGraph.
    """
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _fmt(result: dict | list) -> str:
    """Turn a cart service response into a readable string for the LLM."""
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}. {result.get('detail', '')}"
    return json.dumps(result, indent=2)


@tool
def cart_add(user_id: str, restaurant_id: str, dish_id: str, quantity: int = 1) -> str:
    """
    Add a dish to the user's cart.
    """
    result = _run_safe(_add(user_id, restaurant_id, dish_id, quantity))
    return _fmt(result)


@tool
def cart_update(user_id: str, restaurant_id: str, dish_id: str, quantity: int) -> str:
    """
    Update the quantity of a dish already in the cart.
    """
    result = _run_safe(_update(user_id, restaurant_id, dish_id, quantity))
    return _fmt(result)


@tool
def cart_remove(user_id: str, restaurant_id: str, dish_id: str) -> str:
    """Remove a specific dish from the cart entirely."""
    result = _run_safe(_remove(user_id, restaurant_id, dish_id))
    return _fmt(result)


@tool
def cart_clear(user_id: str, restaurant_id: str) -> str:
    """Clear the user's entire cart."""
    result = _run_safe(_clear(user_id, restaurant_id))
    return _fmt(result)


@tool
def cart_view(user_id: str, restaurant_id: str) -> str:
    """
    Get the current contents of the user's cart with items and total.
    Always call this before placing an order.
    """
    result = _run_safe(_view(user_id, restaurant_id))
    return _fmt(result)