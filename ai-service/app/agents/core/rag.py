# app/agents/core/rag.py
import os
from sentence_transformers import SentenceTransformer
from app.repositories.db.pgvector import search_menu, search_order_history

# Same model as ingest.py — MUST match!
model_path = "/app/models/all-MiniLM-L6-v2"
if not os.path.exists(model_path):
    model_path = "all-MiniLM-L6-v2"
embedder = SentenceTransformer(model_path)

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