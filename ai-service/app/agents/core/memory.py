import redis
import json
import os

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

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