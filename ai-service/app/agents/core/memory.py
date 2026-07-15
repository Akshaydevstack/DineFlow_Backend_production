import json

from app.repositories.db.redis import redis_client

def get_session(user_id, restaurant_id):
    key = f"session:{user_id}:{restaurant_id}"
    data = redis_client.get(key)

    if data:
        return json.loads(data)

    return {
        "last_recommendations": [],
        "last_intent": None
    }


def save_session(user_id, restaurant_id, session):
    key = f"session:{user_id}:{restaurant_id}"
    redis_client.setex(key, 1800, json.dumps(session))  # 30 min