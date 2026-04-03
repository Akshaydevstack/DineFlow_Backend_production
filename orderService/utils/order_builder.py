
def build_order_response(order):
    return {
        "order": {
            "order_id": order.public_id,
            "status": order.status,
            "payment_status": order.payment_status,
            "paid_at":order.paid_at,

            # 🔹 Table Info
            "table": {
                "table_number": order.table_number,
                "table_public_id": order.table_public_id,
                "zone_name": order.zone_name,
                "zone_public_id": order.zone_public_id,
            },

            # 🔹 Financials
            "subtotal": str(order.subtotal),
            "tax": str(order.tax),
            "discount": str(order.discount),
            "total": str(order.total),
            "currency": order.currency,

            # 🔹 Timestamps
            "created_at": order.created_at.isoformat(),
            "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
            "preparing_at": order.preparing_at.isoformat() if order.preparing_at else None,
            "ready_at": order.ready_at.isoformat() if order.ready_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "special_request": order.special_request,
            # 🔹 Items
            "items": [
                {
                    "dish_id": item.dish_id,
                    "name": item.dish_name,
                    "unit_price": str(item.unit_price),
                    "quantity": item.quantity,
                    "total": str(item.total_price),
                    "image": item.image_url,
                }
                for item in order.items.all()
            ],
        }
    }