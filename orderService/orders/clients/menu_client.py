import requests
from decimal import Decimal
from django.core.exceptions import ValidationError


class MenuServiceError(Exception):
    pass


def fetch_menu_items(menu_service_url, dish_ids, restaurant_id):
    url = menu_service_url.rstrip("/") + "/internal/dishes/batch/"

    try:
        response = requests.post(
            url,
            json={"dish_ids": dish_ids},
            headers={
                "X-Internal-Call": "true",
                "X-Restaurant-Id": restaurant_id,
            },
            timeout=3,
        )
    except requests.Timeout:
        raise MenuServiceError("Menu service timeout")

    if response.status_code != 200:
        raise MenuServiceError(
            f"Menu service error: {response.status_code}"
        )

    data = response.json()

    return {
        item["dish_id"]: {
            "name": item["name"],
            "price": Decimal(item["price"]),
        }
        for item in data
    }