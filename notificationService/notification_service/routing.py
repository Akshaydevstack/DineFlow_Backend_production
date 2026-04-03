from django.urls import re_path
from .consumers import KitchenDisplayConsumer, WaiterTableSessionConsumer


websocket_urlpatterns = [

    re_path(
        r"ws/kitchen/$",
        KitchenDisplayConsumer.as_asgi(),
    ),

    re_path(
        r"ws/waiter/table-sessions/$",
        WaiterTableSessionConsumer.as_asgi(),
    ),
]