"""
Fix: tool_get_past_orders now includes order_id in every output line
so the agent can use it directly for cancellation without asking the user.

The pgvector metadata for each order must contain order_id.
Your ingest already stores it: metadata={"order_id": order.get("id"), ...}
"""

from langchain_core.tools import tool
from app.agents.core.rag import search_menu_rag, search_order_history_rag
import json

@tool
def tool_search_menu(query: str, restaurant_id: str) -> str:
    """
    Search the restaurant menu semantically.
    Use for dish questions, cravings, price/ingredient/availability queries.

    Args:
        query:         what the user is looking for (e.g. "spicy vegetarian starter")
        restaurant_id: the restaurant's ID

    Returns dish name, price, availability, prep time, dish_id, image, description, tags, and allergens.
    """
    results = search_menu_rag(query, restaurant_id)

    if not results:
        return "No matching dishes found."

    lines = []
    for r in results:
        meta = r.get("metadata", {})
        
        # 1. Safely grab the image URL
        image_url = meta.get("image_url", meta.get("image", ""))
        
        # 2. Build the FIRST line (Inline data separated by | so the parser can read it)
        dish_line = (
            f"- {meta.get('name', 'Unknown')} | "
            f"₹{meta.get('price', 'N/A')} | "
            f"{'✅ Available' if meta.get('available', True) else '❌ Unavailable'} | "
            f"Prep: {meta.get('prep_time', '?')} mins | "
            f"dish_id: {r.get('dish_id', 'Unknown')} | "
            f"image: {image_url}"
        )
        
        # 3. Build the NEXT lines (Multiline data)
        description = meta.get("description", "").strip()
        if description:
            dish_line += f"\n  Description: {description}"
            
        tags = ", ".join(meta.get("tags", []))
        allergens = ", ".join(meta.get("allergens", []))
        
        dish_line += f"\n  Tags: {tags} | Allergens: {allergens}"
        
        lines.append(dish_line)

    return "\n".join(lines)




@tool
def tool_get_past_orders(query: str, user_id: str, limit: int = 10) -> str:
    """
    Retrieve the user's past order history semantically.
    Use when user asks about previous orders, their usual, or wants to reorder.
    If the user specifically asks for their "last" or "most recent" order, pass limit=1.
    """
    results = search_order_history_rag(query, user_id)

    if not results:
        return json.dumps({"error": "No past orders found."})

    # Sort the semantic RAG results by date (Newest First)
    sorted_results = sorted(
        results, 
        key=lambda r: r.get("metadata", {}).get("date", ""), 
        reverse=True
    )

    limited_results = sorted_results[:limit]

    formatted_orders = []
    for r in limited_results:
        meta = r.get("metadata", {})
        
        formatted_orders.append({
            "order_id": meta.get("order_id", meta.get("id", "unknown")),
            "date": meta.get("date", "Unknown Date"),
            "total": meta.get("total", "0.00"),
            "status": meta.get("status", "UNKNOWN"),
            # 👇 This preserves the exact array with 'name', 'quantity', and 'image'!
            "items": meta.get("items", []), 
            "special_request": meta.get("special_request", ""),
            "table_number": meta.get("table_number", "")
        })

    # Return structured data instead of a messy string
    return json.dumps(formatted_orders)