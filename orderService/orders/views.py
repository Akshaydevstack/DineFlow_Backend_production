from django.db.models import Sum, Count
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import OrderCreateSerializer,TableSessionSerializer
from django.db import transaction
from decimal import Decimal
from .models import Order, OrderItem, TableSession
from orders.models import Order, OrderItem
from orders.kafka.producer import publish_order_placed
from common.tenant import get_tenant_context
from orders.redis.idempotency import (
    get_existing_order,
    store_idempotency_key,
)
from rest_framework import serializers
from orders.kafka.producer import publish_order_placed, publish_order_cancelled, publish_session_started
from utils.order_builder import build_order_response
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from .Pagination import orderPagination
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models import Sum
from django.db.models.functions import ExtractHour
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware
from datetime import datetime, timedelta
from django.utils.dateparse import parse_datetime
from orders.kafka.producer import publish_session_closed
from .models import MenuItemSnapshot
import threading



class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})



#=======================
# Internal API
#========================

class AIUserOrdersView(APIView):
   
    authentication_classes = []
    permission_classes = []
 
    def get(self, request):
        user_id       = request.headers.get("X-User-Id")
        restaurant_id = request.headers.get("X-Restaurant-Id")
 
        if not user_id or not restaurant_id:
            return Response(
                {"error": "Missing headers"},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        orders = (
            Order.objects
            .filter(user_id=user_id)
            .order_by("-created_at")[:50]
            .prefetch_related("items")
        )
 
        # Materialize order items ONCE into a flat list
        # This avoids calling order.items.all() twice (double DB hit)
        flat_items = []
        for order in orders:
            timestamp = int(order.created_at.timestamp())
            for item in order.items.all():          # prefetch_related — no extra query
                flat_items.append((timestamp, item))
 
        if not flat_items:
            return Response([], status=status.HTTP_200_OK)
 
        # Single batch snapshot query from the flat list
        dish_ids     = list({item.dish_id for _, item in flat_items})
        snapshots    = MenuItemSnapshot.objects.filter(
            restaurant_id=restaurant_id,
            dish_id__in=dish_ids,
        )
        snapshot_map = {s.dish_id: s for s in snapshots}
 
        results = []
        for timestamp, item in flat_items:
            snapshot = snapshot_map.get(item.dish_id)
            if not snapshot:
                continue
            results.append({
                # Core
                "dish_id":        item.dish_id,
                "name":           snapshot.name,
                "description":    snapshot.description,
                "category_name":  snapshot.category_name,
                # Attributes
                "is_veg":         snapshot.is_veg,
                "is_spicy":       snapshot.is_spicy,
                "is_popular":     snapshot.is_popular,
                "is_trending":    snapshot.is_trending,
                "is_quick_bites": snapshot.is_quick_bites,
                # Quality signals
                "average_rating": snapshot.average_rating,
                "total_orders":   snapshot.total_orders,
                # Context
                "quantity":       item.quantity,
                "timestamp":      timestamp,
            })
 
        return Response(results, status=status.HTTP_200_OK)



# Customer order view
class OrderCreateView (APIView):

    def post(self, request):
        restaurant_id, user_id = get_tenant_context(request)

        # -----------------------------
        # Idempotency Check
        # -----------------------------
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"detail": "Missing Idempotency Key"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_order_id = get_existing_order(user_id, idempotency_key)
        if existing_order_id:
            order = Order.objects.get(public_id=existing_order_id)
            return Response(
                build_order_response(order),
                status=status.HTTP_200_OK,
            )

        serializer = OrderCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        items = validated["items"]
        table_snapshot = validated["table_snapshot"]
        snapshot_map = validated["snapshot_map"]

        # --------------------------------------------------
        # ATOMIC SECTION
        # --------------------------------------------------

        with transaction.atomic():

            session = (
                TableSession.objects
                .select_for_update()
                .filter(
                    restaurant_id=restaurant_id,
                    table_public_id=table_snapshot.table_public_id,
                    status=TableSession.STATUS_ACTIVE,
                )
                .first()
            )

            if session:
                other_user_active_order_exists = session.orders.filter(
                    status__in=[
                        Order.STATUS_CREATED,
                        Order.STATUS_ACCEPTED,
                        Order.STATUS_PREPARING,
                        Order.STATUS_READY,
                        Order.STATUS_PAID,
                    ]
                ).exclude(user_id=user_id).exists()

                if other_user_active_order_exists:
                    raise serializers.ValidationError(
                        {"table_public_id": "This table is currently occupied"}
                    )
            else:
                session = TableSession.objects.create(
                    restaurant_id=restaurant_id,
                    table_public_id=table_snapshot.table_public_id,
                    table_number=table_snapshot.table_number,
                    zone_public_id=table_snapshot.zone_public_id,
                    zone_name=table_snapshot.zone_name,
                )

                transaction.on_commit(
                    lambda: threading.Thread(
                        target=publish_session_started,
                        args=(session, user_id)
                    ).start()
                )

            # --------------------------------------------------
            # Create Order attached to session
            # --------------------------------------------------
            order = Order.objects.create(
                user_id=user_id,
                restaurant_id=restaurant_id,
                session=session,
                status=Order.STATUS_CREATED,
                special_request=validated.get("special_request", ""),
                table_number=session.table_number,
                table_public_id=session.table_public_id,
                zone_name=session.zone_name,
                zone_public_id=session.zone_public_id,
            )

            order_items = []

            for item in items:
                snap = snapshot_map[item["dish_id"]]
                quantity = int(item["quantity"])
                unit_price = Decimal(snap.price)

                order_items.append(
                    OrderItem(
                        order=order,
                        dish_id=snap.dish_id,
                        dish_name=snap.name,
                        unit_price=unit_price,
                        quantity=quantity,
                        total_price=unit_price * quantity,
                        image_url=snap.image_url,
                    )
                )

            OrderItem.objects.bulk_create(order_items)

            order.recalculate_totals()

            # ⚡ FIX 2: Run order placed event in a background thread
            transaction.on_commit(
                lambda: threading.Thread(
                    target=publish_order_placed, 
                    args=(order,)
                ).start()
            )

            store_idempotency_key(
                user_id=user_id,
                key=idempotency_key,
                order_id=order.public_id,
            )

        return Response(
            build_order_response(order),
            status=status.HTTP_201_CREATED,
        )



# List all the orders for the user

class OrderListView(APIView):

    def get(self, request):
        user_id = request.headers.get("X-User-Id")

        orders = (
            Order.objects
            .filter(user_id=user_id)
            .order_by("-created_at")
            .prefetch_related("items")
        )

        return Response(
            {
                "orders": [
                    build_order_response(order)["order"]
                    for order in orders
                ]
            }
        )


class OrderCancelView(APIView):

    def post(self, request, public_id):
        restaurant_id, user_id = get_tenant_context(request)

        order = Order.objects.filter(
            public_id=public_id,
            user_id=user_id
        ).select_related("session").first()

        if not order:
            return Response(
                {"detail": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status not in [
            Order.STATUS_CREATED,
            Order.STATUS_ACCEPTED,
            Order.STATUS_PREPARING,
            Order.STATUS_PAID,
        ]:
            return Response(
                {
                    "detail": f"Order cannot be cancelled in '{order.status}' state"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():

            # ✅ This triggers session auto-close logic
            order.update_status(Order.STATUS_CANCELLED)

            transaction.on_commit(
                lambda: publish_order_cancelled(order)
            )

        return Response(
            build_order_response(order),
            status=status.HTTP_200_OK,
        )


class OrderDetailView(APIView):

    def get(self, request, public_id):
        restaurant_id, user_id = get_tenant_context(request)

        order = (
            Order.objects
            .filter(
                public_id=public_id,
                user_id=user_id
            )
            .prefetch_related("items")
            .first()
        )

        if not order:
            return Response(
                {"detail": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            build_order_response(order),
            status=status.HTTP_200_OK,
        )


# ==============
# Waiter views
# ==============


class WaiterOrderListView(APIView):

    def get(self, request):
        user_id = request.headers.get("X-User-Id")
        status_param = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        zone = request.GET.get("zone")
        table = request.GET.get("table")
        search = request.GET.get("search")

        queryset = (
            Order.objects.filter(user_id=user_id)
            .select_related("session")
            .prefetch_related("items")
            .order_by("-created_at")
        )

        # ------------------------------------
        # Filtering
        # ------------------------------------

        if status_param:
            queryset = queryset.filter(status=status_param)

        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        if zone:
            queryset = queryset.filter(zone_public_id=zone)

        if table:
            queryset = queryset.filter(table_public_id=table)

        # ------------------------------------
        # Search
        # ------------------------------------

        if search:
            queryset = queryset.filter(
                Q(public_id__icontains=search) |
                Q(table_number__icontains=search) |
                Q(waiter_name__icontains=search) |
                Q(items__dish_name__icontains=search)
            ).distinct()

        # ------------------------------------
        # Pagination
        # ------------------------------------

        paginator = orderPagination()
        page = paginator.paginate_queryset(queryset, request)

        data = [
            build_order_response(order)["order"]
            for order in page
        ]

        return paginator.get_paginated_response(data)




class WaiterTableCheckoutDetailView(APIView):

    def get(self, request, table_public_id):

        ongoing_statuses = [
            Order.STATUS_CREATED,
            Order.STATUS_ACCEPTED,
            Order.STATUS_PREPARING,
            Order.STATUS_READY,
            Order.STATUS_PAID,
        ]

        orders = (
            Order.objects
            .filter(
                table_public_id=table_public_id,
                status__in=ongoing_statuses,
            )
            .select_related("session")
            .prefetch_related("items")
            .order_by("created_at")
        )

        if not orders.exists():
            return Response(
                {"detail": "No ongoing orders for this table"},
                status=status.HTTP_404_NOT_FOUND,
            )

        session = orders.first().session

        # -----------------------------------
        # Aggregation variables
        # -----------------------------------
        total_subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")
        grand_total = Decimal("0.00")
        total_items = 0

        orders_data = []

        for order in orders:

            total_subtotal += order.subtotal
            total_tax += order.tax
            total_discount += order.discount
            grand_total += order.total

            items_data = []

            for item in order.items.all():
                total_items += item.quantity

                items_data.append({
                    "dish_id": item.dish_id,
                    "dish_name": item.dish_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "total_price": float(item.total_price),
                })

            orders_data.append({
                "order_id": order.public_id,
                "orderby_user_id": order.user_id,
                "status": order.status,
                "payment_status": order.payment_status,
                "waiter": {
                    "id": order.waiter_id,
                    "name": order.waiter_name,
                },
                "timestamps": {
                    "created_at": order.created_at,
                    "accepted_at": order.accepted_at,
                    "preparing_at": order.preparing_at,
                    "ready_at": order.ready_at,
                },
                "financials": {
                    "subtotal": float(order.subtotal),
                    "tax": float(order.tax),
                    "discount": float(order.discount),
                    "total": float(order.total),
                },
                "special_request": order.special_request,
                "items": items_data,
            })

        response_data = {
            "table": {
                "table_public_id": table_public_id,
                "table_number": session.table_number,
                "zone_name": session.zone_name,
            },
            "session": {
                "session_id": session.public_id,
                "status": session.status,
                "started_at": session.started_at,
                "last_activity_at": session.last_activity_at,
            },
            "summary": {
                "orders_count": orders.count(),
                "total_items": total_items,
                "subtotal": float(total_subtotal),
                "tax": float(total_tax),
                "discount": float(total_discount),
                "grand_total": float(round(grand_total, 2)),
                "currency": orders.first().currency,
            },
            "orders": orders_data,
        }

        return Response(response_data)
    
# ==============
# Admin views
# ==============


class AdminOrderListView(APIView):

    def get(self, request):

        status_param = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        zone = request.GET.get("zone")
        table = request.GET.get("table")
        search = request.GET.get("search")
        ordering = request.GET.get("ordering", "-created_at")

        # Date range  — expect "YYYY-MM-DD" strings
        created_at_after = request.GET.get(
            "created_at_after")   # from (inclusive)
        created_at_before = request.GET.get(
            "created_at_before")  # to   (inclusive)

        queryset = (
            Order.objects
            .select_related("session")
            .prefetch_related("items")
        )

        # -----------------------------
        # Filtering
        # -----------------------------
        if status_param:
            queryset = queryset.filter(status=status_param)

        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        if zone:
            queryset = queryset.filter(zone_public_id=zone)

        if table:
            queryset = queryset.filter(table_public_id=table)

        # -----------------------------
        # Date Range Filter
        # -----------------------------
        if created_at_after:
            # gte the start of that day (00:00:00 UTC)
            queryset = queryset.filter(created_at__date__gte=created_at_after)

        if created_at_before:
            # lte the end of that day (23:59:59 UTC)
            queryset = queryset.filter(created_at__date__lte=created_at_before)

        # -----------------------------
        # Search
        # -----------------------------
        if search:
            queryset = queryset.filter(
                Q(public_id__icontains=search) |
                Q(table_number__icontains=search) |
                Q(waiter_name__icontains=search) |
                Q(user_id__icontains=search) |
                Q(items__dish_name__icontains=search)
            ).distinct()

        # -----------------------------
        # Ordering
        # -----------------------------
        ALLOWED_ORDERING = [
            "created_at",
            "total",
            "status",
            "payment_status",
        ]

        ordering_field = ordering.lstrip("-")
        if ordering_field not in ALLOWED_ORDERING:
            ordering = "-created_at"

        queryset = queryset.order_by(ordering)

        # -----------------------------
        # Pagination
        # -----------------------------
        paginator = orderPagination()
        page = paginator.paginate_queryset(queryset, request)

        data = [
            build_order_response(order)["order"]
            for order in page
        ]

        return paginator.get_paginated_response(data)


# for admin status update

class AdminOrderStatusUpdateView(APIView):

    def patch(self, request, public_id):

        new_status = request.data.get("status")

        if not new_status:
            return Response(
                {"detail": "Status is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order = (
            Order.objects
            .filter(
                public_id=public_id
            )
            .select_related("session")
            .first()
        )

        if not order:
            return Response(
                {"detail": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            order.update_status(new_status)
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            build_order_response(order),
            status=status.HTTP_200_OK,
        )


# For admin to accept the payment

class AdminOrderPaymentUpdateView(APIView):

    def patch(self, request, public_id):

        order = Order.objects.filter(
            public_id=public_id,
        ).first()

        if not order:
            return Response(
                {"detail": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        payment_status = request.data.get("payment_status")

        if payment_status not in [
            Order.PAYMENT_PENDING,
            Order.PAYMENT_PAID,
            Order.PAYMENT_FAILED,
        ]:
            return Response(
                {"detail": "Invalid payment status"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.payment_status = payment_status

        if payment_status == Order.PAYMENT_PAID:
            order.paid_at = timezone.now()

        order.save(update_fields=["payment_status", "paid_at"])

        return Response(
            build_order_response(order),
            status=status.HTTP_200_OK,
        )


# For showing the status of the order

class AdminOrderStatsView(APIView):

    def get(self, request):

        qs = Order.objects.all()

        stats = qs.aggregate(
            total_orders=Count("id"),

            created=Count("id", filter=Q(status=Order.STATUS_CREATED)),
            accepted=Count("id", filter=Q(status=Order.STATUS_ACCEPTED)),
            preparing=Count("id", filter=Q(status=Order.STATUS_PREPARING)),
            ready=Count("id", filter=Q(status=Order.STATUS_READY)),
            paid=Count("id", filter=Q(status=Order.STATUS_PAID)),
            completed=Count("id", filter=Q(status=Order.STATUS_COMPLETED)),
            cancelled=Count("id", filter=Q(status=Order.STATUS_CANCELLED)),

            payment_pending=Count(
                "id", filter=Q(payment_status=Order.PAYMENT_PENDING)
            ),
            payment_paid=Count(
                "id", filter=Q(payment_status=Order.PAYMENT_PAID)
            ),
            payment_failed=Count(
                "id", filter=Q(payment_status=Order.PAYMENT_FAILED)
            ),
        )

        # Derived metrics
        stats["active_orders"] = (
            stats["created"]
            + stats["accepted"]
            + stats["preparing"]
            + stats["ready"]
            + stats["paid"]
        )

        return Response(stats)


# Hourly sales data for
class AdminHourlySalesView(APIView):

    def get(self, request):

        date_str = request.GET.get("date")
        if date_str:
            target_date = parse_date(date_str)
            if not target_date:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.now().date()

        start = make_aware(datetime.combine(target_date, datetime.min.time()))
        end = start + timedelta(days=1)

        # Base queryset
        base_qs = (
            Order.objects
            .filter(
                payment_status=Order.PAYMENT_PAID,
                paid_at__gte=start,
                paid_at__lt=end,
            )
            .select_related("session")
            .prefetch_related("items")
        )

        # Aggregate per hour
        hourly_aggregate = (
            base_qs
            .annotate(hour=ExtractHour("paid_at"))
            .values("hour")
            .annotate(
                orders=Count("id"),
                sales=Sum("total"),
            )
            .order_by("hour")
        )

        # Fetch actual orders and group them
        orders_with_hour = (
            base_qs
            .annotate(hour=ExtractHour("paid_at"))
            .order_by("hour", "-paid_at")
        )

        # Build hour -> orders map
        hour_map = {}

        for order in orders_with_hour:
            hour = order.hour

            if hour not in hour_map:
                hour_map[hour] = []

            hour_map[hour].append({
                "order_id": order.public_id,
                "table": order.table_number,
                "total": round(float(order.total), 2),
                "paid_at": order.paid_at,
                "items": [
                    {
                        "dish_name": item.dish_name,
                        "quantity": item.quantity,
                        "price": round(float(item.total_price), 2),
                    }
                    for item in order.items.all()
                ]
            })

        # Final structured response
        hourly_sales = []

        total_orders = 0
        total_revenue = 0

        for entry in hourly_aggregate:
            hour = entry["hour"]
            orders_count = entry["orders"]
            sales = round(float(entry["sales"]), 2)

            total_orders += orders_count
            total_revenue += sales

            hourly_sales.append({
                "hour": f"{hour:02d}:00",
                "orders": orders_count,
                "sales": sales,
                "order_details": hour_map.get(hour, []),
            })

        avg_order_value = round(
            total_revenue / total_orders, 2
        ) if total_orders else 0

        return Response({
            "date": str(target_date),
            "hourly_sales": hourly_sales,
            "daily_totals": {
                "orders": total_orders,
                "revenue": round(total_revenue, 2),
                "avgOrderValue": avg_order_value,
            }
        })


# Top Dishes that are pub

class AdminTopDishesView(APIView):

    def get(self, request):
        date_str = request.GET.get("date")

        filters = {
            "order__payment_status": Order.PAYMENT_PAID,
        }

        # If date provided → filter by that date
        if date_str:
            target_date = parse_date(date_str)
            if not target_date:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            start = make_aware(datetime.combine(
                target_date, datetime.min.time()))
            end = start + timedelta(days=1)

            filters["order__paid_at__gte"] = start
            filters["order__paid_at__lt"] = end

        # Aggregate Top 5 dishes
        top_dishes = (
            OrderItem.objects
            .filter(**filters)
            .values("dish_id", "dish_name")
            .annotate(
                total_quantity=Sum("quantity"),
                total_revenue=Sum("total_price"),
            )
            .order_by("-total_quantity")[:5]
        )

        result = [
            {
                "dish_id": dish["dish_id"],
                "dish_name": dish["dish_name"],
                "total_quantity": dish["total_quantity"],
                "total_revenue": round(float(dish["total_revenue"]), 2),
            }
            for dish in top_dishes
        ]

        return Response({
            "date": date_str if date_str else "all-time",
            "top_5_dishes": result
        })


# To get a user orders


class RestaurantAdminOrderUserListView(APIView):

    def get(self, request, user_id):
        orders = (
            Order.objects
            .filter(user_id=user_id)
            .order_by("-created_at")
            .prefetch_related("items")
        )

        return Response(
            {
                "orders": [
                    build_order_response(order)["order"]
                    for order in orders
                ]
            }
        )



# for seeing the current on going table

class AdminTableOrdersView(APIView):

    def get(self, request, table_public_id):

        ongoing_only = request.GET.get("ongoing_only", "false").lower() == "true"

        queryset = (
            Order.objects
            .filter(table_public_id=table_public_id)
            .select_related("session")
            .prefetch_related("items")
            .order_by("-created_at")
        )

        # -----------------------------------
        # Ongoing filter
        # -----------------------------------
        if ongoing_only:
            queryset = queryset.filter(
                status__in=[
                    Order.STATUS_CREATED,
                    Order.STATUS_ACCEPTED,
                    Order.STATUS_PREPARING,
                    Order.STATUS_READY,
                    Order.STATUS_PAID,
                ]
            )

        return Response({
            "table_public_id": table_public_id,
            "ongoing_only": ongoing_only,
            "orders": [
                build_order_response(order)["order"]
                for order in queryset
            ]
        })


# out view for bill

# ============================================
# Admin - Full Checkout Bill Details View
# ============================================

class AdminTableCheckoutDetailView(APIView):

    def get(self, request, table_public_id):

        ongoing_statuses = [
            Order.STATUS_CREATED,
            Order.STATUS_ACCEPTED,
            Order.STATUS_PREPARING,
            Order.STATUS_READY,
            Order.STATUS_PAID,
        ]

        orders = (
            Order.objects
            .filter(
                table_public_id=table_public_id,
                status__in=ongoing_statuses,
            )
            .select_related("session")
            .prefetch_related("items")
            .order_by("created_at")
        )

        if not orders.exists():
            return Response(
                {"detail": "No ongoing orders for this table"},
                status=status.HTTP_404_NOT_FOUND,
            )

        session = orders.first().session

        # -----------------------------------
        # Aggregation variables
        # -----------------------------------
        total_subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")
        grand_total = Decimal("0.00")
        total_items = 0

        orders_data = []

        for order in orders:

            total_subtotal += order.subtotal
            total_tax += order.tax
            total_discount += order.discount
            grand_total += order.total

            items_data = []

            for item in order.items.all():
                total_items += item.quantity

                items_data.append({
                    "dish_id": item.dish_id,
                    "dish_name": item.dish_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "total_price": float(item.total_price),
                })

            orders_data.append({
                "order_id": order.public_id,
                "orderby_user_id": order.user_id,
                "status": order.status,
                "payment_status": order.payment_status,
                "waiter": {
                    "id": order.waiter_id,
                    "name": order.waiter_name,
                },
                "timestamps": {
                    "created_at": order.created_at,
                    "accepted_at": order.accepted_at,
                    "preparing_at": order.preparing_at,
                    "ready_at": order.ready_at,
                },
                "financials": {
                    "subtotal": float(order.subtotal),
                    "tax": float(order.tax),
                    "discount": float(order.discount),
                    "total": float(order.total),
                },
                "special_request": order.special_request,
                "items": items_data,
            })

        response_data = {
            "table": {
                "table_public_id": table_public_id,
                "table_number": session.table_number,
                "zone_name": session.zone_name,
            },
            "session": {
                "session_id": session.public_id,
                "status": session.status,
                "started_at": session.started_at,
                "last_activity_at": session.last_activity_at,
            },
            "summary": {
                "orders_count": orders.count(),
                "total_items": total_items,
                "subtotal": float(total_subtotal),
                "tax": float(total_tax),
                "discount": float(total_discount),
                "grand_total": float(round(grand_total, 2)),
                "currency": orders.first().currency,
            },
            "orders": orders_data,
        }

        return Response(response_data)
    


class AdminTableSessionListView(APIView):

    def get(self, request):

        queryset = TableSession.objects.all()

        restaurant_id = request.GET.get("restaurant_id")
        status_param = request.GET.get("status")
        table_public_id = request.GET.get("table_public_id")
        zone_public_id = request.GET.get("zone_public_id")
        search = request.GET.get("search")

        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")

        # -------- Filters -------- #

        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)

        if status_param:
            queryset = queryset.filter(status=status_param)

        if table_public_id:
            queryset = queryset.filter(table_public_id=table_public_id)

        if zone_public_id:
            queryset = queryset.filter(zone_public_id=zone_public_id)

        if search:
            queryset = queryset.filter(
                Q(table_number__icontains=search)
                | Q(public_id__icontains=search)
            )

        if from_date:
            queryset = queryset.filter(started_at__gte=parse_datetime(from_date))

        if to_date:
            queryset = queryset.filter(started_at__lte=parse_datetime(to_date))

        # -------- Ordering -------- #

        queryset = queryset.order_by("-last_activity_at")

        # -------- Pagination -------- #

        paginator = orderPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        serializer = TableSessionSerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)
    


class CloseTableSessionView(APIView):

    def post(self, request, session_public_id):

        try:
            session = TableSession.objects.get(public_id=session_public_id)
        except TableSession.DoesNotExist:
            return Response(
                {"detail": "Session not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.status == TableSession.STATUS_CLOSED:
            return Response(
                {"detail": "Session already closed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():

            session.status = TableSession.STATUS_CLOSED
            session.closed_at = timezone.now()

            session.save(update_fields=["status", "closed_at"])

            transaction.on_commit(
                lambda: publish_session_closed(session)
            )

        return Response(
            {
                "message": "Session closed successfully",
                "session_id": session.public_id,
                "status": session.status,
            },
            status=status.HTTP_200_OK,
        )