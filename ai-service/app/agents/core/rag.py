# app/agents/core/rag.py
from sentence_transformers import SentenceTransformer
from app.db.pgvector_client import search_menu, search_order_history

# Same model as ingest.py — MUST match!
embedder = SentenceTransformer("/app/models/all-MiniLM-L6-v2")

def search_menu_rag(query: str, restaurant_id: str, top_k: int = 5) -> list:
    """
    Semantic menu search.
    
    Example:
        query = "something spicy and vegetarian under 200"
        returns = [
            {"dish_id": "d1", "content": "...", "metadata": {...}, "similarity": 0.91},
            ...
        ]
    """
    # 1. Embed the query
    query_embedding = embedder.encode(query).tolist()

    # 2. Search pgvector
    results = search_menu(query_embedding, restaurant_id, top_k)

    # 3. Filter out unavailable dishes
    available = [
        r for r in results
        if r["metadata"].get("available", True)
    ]

    return available




def search_order_history_rag(query: str, user_id: str, top_k: int = 20) -> list:
    """
    Search user's past orders semantically.
    
    Example:
        query = "what did I order last time"
        returns = [recent matching orders]
    """
    query_embedding = embedder.encode(query).tolist()
    return search_order_history(query_embedding, user_id, top_k)