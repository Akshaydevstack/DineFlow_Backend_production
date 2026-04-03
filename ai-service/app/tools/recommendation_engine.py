"""
DineFlowOS — AI Recommendations (final)
File: ai-service/app/agents/recommendations.py
"""

import random
import json
import hashlib
import numpy as np
import redis
import os
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Model + Redis — loaded once at startup, shared across all requests
# ---------------------------------------------------------------------------
model = SentenceTransformer("/app/models/all-MiniLM-L6-v2")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis.dineflow-production.svc.cluster.local"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

dish_embedding_cache: dict = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def dish_to_text(dish: dict) -> str:
    """Converts a dish dict into a descriptive text string for embedding.
       Handles both API formats (boolean flags) and RAG DB formats (tags list).
    """
    parts = []
    
    if dish.get("name"):           parts.append(dish["name"])
    if dish.get("description"):    parts.append(dish["description"])
    if dish.get("category_name"):  parts.append(dish["category_name"])
    if dish.get("category"):       parts.append(dish["category"]) 

    if dish.get("is_veg"):         parts.append("vegetarian")
    elif dish.get("is_veg") is False: parts.append("non-vegetarian")
    if dish.get("is_spicy"):       parts.append("spicy")
    if dish.get("is_trending"):    parts.append("trending")
    if dish.get("is_popular"):     parts.append("popular")
    if dish.get("is_quick_bites"): parts.append("quick bites")

    if dish.get("tags") and isinstance(dish.get("tags"), list):
        parts.extend(dish["tags"])

    clean_parts = []
    for p in parts:
        p_str = str(p).lower().strip()
        if p_str and p_str not in clean_parts:
            clean_parts.append(p_str)

    return ", ".join(clean_parts)


def get_dish_id(item: dict) -> str:
    return item.get("dish_id") or item.get("public_id") or item.get("id") or ""


def get_dish_embedding(dish: dict) -> np.ndarray:
    pid = dish.get("public_id") or dish.get("dish_id", "")
    if pid and pid in dish_embedding_cache:
        return dish_embedding_cache[pid]
    embedding = model.encode(dish_to_text(dish))
    if pid:
        dish_embedding_cache[pid] = embedding
    return embedding


def make_cache_key(user_id: str, restaurant_id: str, views: list, cart: list, orders: list) -> str:
    signal_ids = sorted([get_dish_id(v) for v in views])
    cart_ids   = sorted([get_dish_id(c) for c in cart])
    order_ids  = sorted([get_dish_id(o) for o in orders])
    raw        = f"{user_id}:{restaurant_id}:{signal_ids}:{cart_ids}:{order_ids}"
    hash_key   = hashlib.md5(raw.encode()).hexdigest()
    return f"recommendations:{hash_key}"


# ---------------------------------------------------------------------------
# Main recommendation function
# ---------------------------------------------------------------------------
def get_ai_recommendations_sync(views, cart, orders, dishes, user_id: str = "", restaurant_id: str = "") -> list:

    if not dishes:
        return []

    cart   = cart   if isinstance(cart,   list) else cart   or []
    orders = orders if isinstance(orders, list) else orders or []
    views  = views  if isinstance(views,  list) else views  or []

    cache_key = make_cache_key(user_id, restaurant_id, views, cart, orders)
    try:
        cached = redis_client.get(cache_key)
        if cached:
            cached_ids = json.loads(cached)
            dish_map   = {d.get("public_id", d.get("dish_id")): d for d in dishes}
            return [dish_map[pid] for pid in cached_ids if pid in dish_map]
    except Exception as e:
        pass

    views  = sorted(views,  key=lambda x: x.get("timestamp", 0), reverse=True)[:20]
    orders = sorted(orders, key=lambda x: x.get("timestamp", 0), reverse=True)[:20]

    profile_parts = []
    for v in views:
        txt = dish_to_text(v)
        if txt: profile_parts.append(txt)
    for c in cart:
        txt = dish_to_text(c)
        if txt: profile_parts.extend([txt] * 3)
    for o in orders:
        txt = dish_to_text(o)
        if txt: profile_parts.extend([txt] * 5)

    # ✅ Fallback: Sort by rating AND total orders
    if not profile_parts:
        return sorted(
            dishes,
            key=lambda d: (float(d.get("average_rating") or 0), int(d.get("total_orders") or 0)),
            reverse=True,
        )[:10]

    profile_embeddings = model.encode(profile_parts)
    user_vector        = np.mean(profile_embeddings, axis=0)

    seen_ids = {get_dish_id(x) for x in (views + cart + orders) if get_dish_id(x)}

    candidates = [d for d in dishes if get_dish_id(d) not in seen_ids]
    if not candidates:
        candidates = dishes

    dish_embeddings = np.array([get_dish_embedding(d) for d in candidates])
    user_norm  = user_vector / (np.linalg.norm(user_vector) + 1e-9)
    dish_norms = dish_embeddings / (np.linalg.norm(dish_embeddings, axis=1, keepdims=True) + 1e-9)
    scores = dish_norms @ user_norm

    ranked_indices = np.argsort(scores)[::-1][:8]
    results        = [candidates[i] for i in ranked_indices]

    result_pub_ids = {get_dish_id(d) for d in results}
    explore_pool = [d for d in dishes if get_dish_id(d) not in result_pub_ids and get_dish_id(d) not in seen_ids]
    explore        = random.sample(explore_pool, min(2, len(explore_pool)))
    results.extend(explore)

    try:
        result_ids = [get_dish_id(d) for d in results]
        redis_client.setex(cache_key, 300, json.dumps(result_ids))
    except Exception as e:
        pass

    return results[:10]