import logging
from tickets.models import KitchenTicket,KitchenItem

logger = logging.getLogger(__name__)


def handle_order_placed(event,tenant_id):
    order_id = event["order_id"]

    if KitchenTicket.objects.filter(order_id=order_id).exists():
        logger.warning(f"Kitchen ticket already exists for {order_id}")
        return

   
    ticket = KitchenTicket.objects.create(
        order_id=order_id,
        user_id=event["user_id"],
        restaurant_id=tenant_id
    )

    items = event.get("items", [])

    for item in items:
        KitchenItem.objects.create(
            ticket=ticket,
            dish_id=item["dish_id"],
            dish_name=item["dish_name"],
            quantity=item["quantity"],
            restaurant_id=tenant_id
        )

    logger.info(
        f"✅ Kitchen ticket created for order {order_id} "
        f"with {len(items)} items"
    )

    return ticket



def handle_order_cancelled(event):
    order_id = event["order_id"]

    try:
        ticket = KitchenTicket.objects.get(order_id=order_id)
    except KitchenTicket.DoesNotExist:
        logger.warning(f"No kitchen ticket found for cancelled order {order_id}")
        return None

    ticket.cancel()

    logger.info(f"🛑 Kitchen ticket cancelled for order {order_id}")

    return ticket