from channels.generic.websocket import AsyncWebsocketConsumer
import json

class KitchenDisplayConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        headers = dict(self.scope["headers"])

        restaurant_id = headers.get(b"x-restaurant-id")

        if not restaurant_id:
            await self.close()
            return

        self.restaurant_id = restaurant_id.decode()
        self.group_name = f"kitchen_display_{self.restaurant_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_ticket_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))


# consumers.py

class WaiterTableSessionConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        headers = dict(self.scope["headers"])
        restaurant_id = headers.get(b"x-restaurant-id")

        if not restaurant_id:
            await self.close()
            return

        self.restaurant_id = restaurant_id.decode()

        self.group_name = f"waiter_table_sessions_{self.restaurant_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):

        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_session_update(self, event):

        await self.send(
            text_data=json.dumps(event["data"])
        )


# update waiter orders once order created
class WaiterDisplayConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        headers = dict(self.scope["headers"])
        restaurant_id = headers.get(b"x-restaurant-id")

        if not restaurant_id:
            await self.close()
            return

        self.restaurant_id = restaurant_id.decode()
        self.group_name = f"waiter_display_{self.restaurant_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def new_order_alert(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_order_alert",
            "data": event["data"]
        }))



class AdminTableConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        headers = dict(self.scope["headers"])
        restaurant_id = headers.get(b"x-restaurant-id")

        if not restaurant_id:
            await self.close()
            return

        self.restaurant_id = restaurant_id.decode()
        self.group_name = f"admin_tables_{self.restaurant_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    # Triggered by channel_layer.group_send(..., {"type": "send_table_update"})
    async def send_table_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "admin_table_update",
            "data": event["data"]
        }))


class AdminOrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        headers = dict(self.scope["headers"])
        restaurant_id = headers.get(b"x-restaurant-id")

        if not restaurant_id:
            await self.close()
            return

        self.restaurant_id = restaurant_id.decode()
        self.group_name = f"admin_orders_{self.restaurant_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    # Triggered by channel_layer.group_send(..., {"type": "send_order_update"})
    async def send_order_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "admin_order_update",
            "data": event["data"]
        }))