import redis
import json
from django.conf import settings
import requests
from decimal import Decimal
import os

# redis_client = redis.Redis(
#     host=settings.REDIS_HOST,
#     port=settings.REDIS_PORT,
#     decode_responses=True,
# )

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis.dineflow-production.svc.cluster.local"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

CART_TTL = 60 * 60 * 24


def get_cart_key(restaurant_id, user_id):
    return f"cart:{restaurant_id}:{user_id}"


def get_cart(restaurant_id, user_id):
    key = get_cart_key(restaurant_id, user_id)
    data = redis_client.get(key)
    return json.loads(data) if data else {}


def save_cart(restaurant_id, user_id, cart):
    key = get_cart_key(restaurant_id, user_id)
    redis_client.setex(key, CART_TTL, json.dumps(cart))


def validate_dish(menu_service_url, dish_id, restaurant_id):
    base = menu_service_url.rstrip("/")
    response = requests.get(
        f"{base}/internal/dishes/{dish_id}/",
        headers={
            "X-Restaurant-Id": restaurant_id,
            "X-Internal-Call": "true",
        },
        timeout=3,
    )

    if response.status_code != 200:
        raise ValueError("Invalid dish")

    return response.json()

from decimal import Decimal, ROUND_HALF_UP

def build_cart_response(cart):
    items = []
    subtotal = Decimal("0.00")
    original_subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")

    for dish_id, data in cart.items():
        price = Decimal(str(data["price"]))
        quantity = int(data["quantity"])
        total = price * quantity
        subtotal += total

        image = data["image"]
        original_price_value = data.get("original_price")

        item_discount = Decimal("0.00")
        item_discount_percentage = Decimal("0")

        if original_price_value and original_price_value != "None":
            original_price = Decimal(str(original_price_value))

           
            if original_price > price:
                original_total = original_price * quantity
                original_subtotal += original_total

                item_discount = (original_price - price) * quantity
                total_discount += item_discount

                # Item percentage
                item_discount_percentage = (
                    ((original_price - price) / original_price) * 100
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            else:
                original_subtotal += total
        else:
            original_subtotal += total

        items.append({
            "dish_id": dish_id,
            "name": data["name"],
            "price": str(price),
            "quantity": quantity,
            "total": str(total),
            "image": image,
            "original_price": original_price_value,
            "item_discount": str(item_discount),
            "item_discount_percentage": str(item_discount_percentage),
        })

    cart_discount_percentage = Decimal("0")

    if original_subtotal > 0:
        cart_discount_percentage = (
            (total_discount / original_subtotal) * 100
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return {
        "items": items,
        "subtotal": str(subtotal),
        "original_subtotal": str(original_subtotal),
        "total_discount": str(total_discount),
        "cart_discount_percentage": str(cart_discount_percentage),
    }


def clear_cart(restaurant_id, user_id):
    key = get_cart_key(restaurant_id, user_id)
    redis_client.delete(key)
