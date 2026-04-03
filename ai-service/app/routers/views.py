from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from google.api_core.exceptions import ResourceExhausted
from loguru import logger
import asyncio
from typing import List, Dict, Any

from app.tools.dynamo_tools import store_dish_view, get_user_history
from app.tools.menu_client import fetch_menu_dishes
from app.tools.cart_client import fetch_user_cart
from app.tools.order_client import fetch_user_orders
from app.tools.recommendation_engine import get_ai_recommendations_sync
from app.agents.core.agent import run_agent

router = APIRouter()

# ---------------------------------------------------
# Request Models
# ---------------------------------------------------

class WaiterRequest(BaseModel):
    message: str

class TrackViewRequest(BaseModel):
    dish: Dict[str, Any] # Specify exactly what dish should look like if possible

# Removed unused Ingest models (add them back if you have endpoints for them)

# ---------------------------------------------------
# Endpoints
# ---------------------------------------------------

@router.post("/track-view/")
async def track_view(
    payload: TrackViewRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_restaurant_id: str = Header(..., alias="X-Restaurant-Id")
):
    # Run synchronous DB call in a thread
    await asyncio.to_thread(store_dish_view, x_user_id, payload.dish, x_restaurant_id)
    return {"message": "view tracked"}


@router.get("/recommendations/")
async def get_recommendations(
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_restaurant_id: str = Header(..., alias="X-Restaurant-Id")
):
    # The headers are guaranteed to exist now due to the `...` default in Header()

    # If get_user_history is synchronous, wrap it. If it's async, just await it.
    views = await asyncio.to_thread(get_user_history, x_user_id) 
    
    # Assuming these are async functions based on your original code
    cart = await fetch_user_cart(x_user_id, x_restaurant_id)
    orders = await fetch_user_orders(x_user_id, x_restaurant_id)
    dishes = await fetch_menu_dishes(x_restaurant_id)

    if not dishes:
        return []

    if not views and not cart and not orders:
        # Fallback for new users
        return sorted(
            dishes,
            key=lambda d: float(d.get("average_rating") or 0),
            reverse=True
        )[:10]

    try:
        # ✅ CRITICAL FIX: Run synchronous recommendation engine in a background thread
        # This prevents FastAPI from freezing and failing Kubernetes health checks!
        return await asyncio.to_thread(
            get_ai_recommendations_sync,
            views, cart, orders, dishes,
            user_id=x_user_id,
            restaurant_id=x_restaurant_id
        )
    except Exception as e:
        logger.error(f"Recommendation error, falling back: {e}")
        return sorted(
            dishes,
            key=lambda d: float(d.get("average_rating") or 0),
            reverse=True
        )[:10]


# ---------------------------------------------------
# AI Waiter
# ---------------------------------------------------
@router.post("/ai-waiter/")
async def ai_waiter_endpoint(
    payload: WaiterRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_restaurant_id: str = Header(..., alias="X-Restaurant-Id"),
    x_table_id: str = Header(..., alias="X-Table-Id"),
):
    # No manual None checks needed; FastAPI handles validation automatically

    try:
        # Use asyncio.to_thread for safer thread pooling
        result = await asyncio.to_thread(
            run_agent,
            user_id=x_user_id,
            restaurant_id=x_restaurant_id,
            table_public_id=x_table_id,
            message=payload.message,
        )
        return result

    # ✅ FIXED: Catch Google's specific Rate Limit exception
    except ResourceExhausted:
        logger.warning(f"Google API Rate Limit hit for user {x_user_id}")
        raise HTTPException(status_code=429, detail="AI is busy, please try again in a few minutes")

    except Exception as e:
        logger.exception(f"Waiter endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong")