import boto3
import time
import json
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from app.core import config
from app.repositories.db.redis import redis_client

dynamodb = boto3.resource(
    "dynamodb",
    region_name=config.AWS_DEFAULT_REGION
)

table = dynamodb.Table("dish_views")


def store_dish_view(user_id: str, dish: dict, x_restaurant_id: str):
    item = {
        "user_id": str(user_id),
        "timestamp": int(time.time()),
        "dish_id": dish.get("public_id"),
        "name": dish.get("name"),
        "category": dish.get("category"),
        "category_name": dish.get("category_name"),
        "is_spicy": dish.get("is_spicy", False),
        "is_veg": dish.get("is_veg", True),
        "price": Decimal(str(dish.get("price", 0))),
        "prep_time": int(dish.get("prep_time", 0)),
        "restaurant_id": str(x_restaurant_id),
        "event_type": "view"
    }

    try:
        table.put_item(Item=item)
    except Exception as e:
        print(f"Failed to put item in DynamoDB: {e}")
        
    try:
        cache_key = f"user_history:{user_id}"
        redis_client.delete(cache_key)
    except Exception as e:
        print(f"Redis invalidation error: {e}")


def get_user_history(user_id: str, limit: int = 50) -> list:
    cache_key = f"user_history:{user_id}"

    # Check cache first
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis read error: {e}")

    # Fetch from DynamoDB
    try:
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(str(user_id)),
            ScanIndexForward=False,
            Limit=limit
        )
        items = response.get("Items", [])

        # Cache for 2 minutes
        try:
            redis_client.setex(cache_key, 120, json.dumps(items, default=str))
        except Exception as e:
            print(f"Redis write error: {e}")

        return items
    except Exception as e:
        print("DynamoDB error:", e)
        return []
