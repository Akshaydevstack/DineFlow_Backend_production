from django.urls import re_path
from .consumers import (
    KitchenDisplayConsumer, 
    WaiterTableSessionConsumer, 
    WaiterDisplayConsumer,
    AdminTableConsumer,       # 🟢 NEW
    AdminOrderConsumer        # 🟢 NEW
)

websocket_urlpatterns = [
    re_path(
        r"^ws/kitchen/$",
        KitchenDisplayConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/waiter/table-sessions/$",
        WaiterTableSessionConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/waiter-display/$",
        WaiterDisplayConsumer.as_asgi(),
    ),
    # 🟢 NEW: Admin Routes
    re_path(
        r"^ws/restaurant-admin/tables/$",
        AdminTableConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/restaurant-admin/orders/$",
        AdminOrderConsumer.as_asgi(),
    ),
]