from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import KitchenTicket, KitchenItem
from .serializers import (
    KitchenTicketListSerializer,
    KitchenTicketDetailSerializer,
    KitchenItemSerializer
)
from rest_framework.generics import ListAPIView
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .Pagination import TicketPagination
from django.db.models import Count, Q
from .filters import KitchenTicketFilter
from .kafka.producer import publish_kitchen_event
from django.utils import timezone
from datetime import datetime
# Create your views here.


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})



class KitchenTicketListView(APIView):

    def get(self, request):
        queryset = KitchenTicket.objects.prefetch_related("items").all()

        restaurant_id = request.GET.get("restaurant_id")
        status_param = request.GET.get("status")
        order_id = request.GET.get("order_id")
        search = request.GET.get("search")

        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")

        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)

        if status_param:
            queryset = queryset.filter(status=status_param)

        if order_id:
            queryset = queryset.filter(order_id=order_id)

        if search:
            queryset = queryset.filter(
                Q(order_id__icontains=search) |
                Q(public_id__icontains=search) |
                Q(user_id__icontains=search)
            )

        # =============================
        # DATE FILTER LOGIC
        # =============================

        if from_date and to_date:
            queryset = queryset.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date
            )
        else:
            # Default: today only
            today = timezone.now().date()
            queryset = queryset.filter(created_at__date=today)

        queryset = queryset.order_by("-created_at")

        serializer = KitchenTicketListSerializer(queryset, many=True)

        return Response(serializer.data)


class KitchenTicketDetailView(APIView):

    def get(self, request, public_id):
        ticket = get_object_or_404(
            KitchenTicket.objects.prefetch_related("items"),
            public_id=public_id
        )
        serializer = KitchenTicketDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class KitchenTicketStatusUpdateView(APIView):

    def post(self, request, public_id):
        ticket = get_object_or_404(KitchenTicket, public_id=public_id)
        new_status = request.data.get("status")

        try:
            if new_status == KitchenTicket.STATUS_ACCEPTED:
                ticket.accept()
            elif new_status == KitchenTicket.STATUS_PREPARING:
                ticket.start_preparing()
            elif new_status == KitchenTicket.STATUS_READY:
                ticket.mark_ready()
            elif new_status == KitchenTicket.STATUS_CANCELLED:
                ticket.cancel()
                publish_kitchen_event("CANCELLED", ticket)
            else:
                return Response(
                    {"error": "Invalid status"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            KitchenTicketDetailSerializer(ticket).data,
            status=status.HTTP_200_OK
        )


class KitchenItemStatusUpdateView(APIView):

    def post(self, request, item_id):
        item = get_object_or_404(KitchenItem, id=item_id)
        new_status = request.data.get("status")

        try:
            if new_status == KitchenItem.STATUS_PREPARING:
                item.start_preparing()
            elif new_status == KitchenItem.STATUS_READY:
                item.mark_ready()
            elif new_status == KitchenItem.STATUS_CANCELLED:
                item.cancel()
            else:
                return Response(
                    {"error": "Invalid status"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            KitchenItemSerializer(item).data,
            status=status.HTTP_200_OK
        )


# =============================
# Admin views
# =============================


class AdminKitchenTicketListView(ListAPIView):
    serializer_class = KitchenTicketListSerializer
    pagination_class = TicketPagination
    # ← use filterset_class, not filterset_fields
    filterset_class = KitchenTicketFilter

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "public_id",
        "order_id"
    ]

    ordering_fields = [
        "created_at",
        "updated_at",
        "status",
    ]

    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            KitchenTicket.objects
            .prefetch_related("items")
            .order_by("-created_at")
        )


# Admin update ticket

class AdminKitchenTicketStatusUpdateView(APIView):

    def post(self, request, public_id):
        restaurant_id = request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise ValidationError("X-Restaurant-Id header missing")

        ticket = get_object_or_404(
            KitchenTicket,
            public_id=public_id,
            restaurant_id=restaurant_id
        )

        new_status = request.data.get("status")

        try:
            if new_status == KitchenTicket.STATUS_ACCEPTED:
                ticket.accept()
            elif new_status == KitchenTicket.STATUS_PREPARING:
                ticket.start_preparing()
            elif new_status == KitchenTicket.STATUS_READY:
                ticket.mark_ready()
            elif new_status == KitchenTicket.STATUS_CANCELLED:
                ticket.cancel()
                publish_kitchen_event("CANCELLED", ticket)
            else:
                raise ValidationError("Invalid status")

        except ValueError as e:
            raise ValidationError(str(e))

        return Response(
            KitchenTicketDetailSerializer(ticket).data,
            status=status.HTTP_200_OK
        )


# Admin update ticket

class AdminKitchenItemStatusUpdateView(APIView):

    def post(self, request, item_id):
        restaurant_id = request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise ValidationError("X-Restaurant-Id header missing")

        item = get_object_or_404(
            KitchenItem,
            id=item_id,
            ticket__restaurant_id=restaurant_id
        )

        new_status = request.data.get("status")

        try:
            if new_status == KitchenItem.STATUS_PREPARING:
                item.start_preparing()
            elif new_status == KitchenItem.STATUS_READY:
                item.mark_ready()
            elif new_status == KitchenItem.STATUS_CANCELLED:
                item.cancel()
            else:
                raise ValidationError("Invalid status")

        except ValueError as e:
            raise ValidationError(str(e))

        return Response(
            KitchenItemSerializer(item).data,
            status=status.HTTP_200_OK
        )

# status for Charts


class AdminKitchenDashboardStatsView(APIView):

    def get(self, request):
        restaurant_id = request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise ValidationError("X-Restaurant-Id header missing")

        # -----------------------------
        # Ticket Aggregations
        # -----------------------------
        tickets = KitchenTicket.objects.filter(
            restaurant_id=restaurant_id
        )

        ticket_stats = tickets.aggregate(
            total=Count("id"),
            received=Count("id", filter=Q(
                status=KitchenTicket.STATUS_RECEIVED)),
            accepted=Count("id", filter=Q(
                status=KitchenTicket.STATUS_ACCEPTED)),
            preparing=Count("id", filter=Q(
                status=KitchenTicket.STATUS_PREPARING)),
            ready=Count("id", filter=Q(status=KitchenTicket.STATUS_READY)),
            cancelled=Count("id", filter=Q(
                status=KitchenTicket.STATUS_CANCELLED)),
        )

        # -----------------------------
        # Item Aggregations
        # -----------------------------
        items = KitchenItem.objects.filter(
            ticket__restaurant_id=restaurant_id
        )

        item_stats = items.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status=KitchenItem.STATUS_PENDING)),
            preparing=Count("id", filter=Q(
                status=KitchenItem.STATUS_PREPARING)),
            ready=Count("id", filter=Q(status=KitchenItem.STATUS_READY)),
            cancelled=Count("id", filter=Q(
                status=KitchenItem.STATUS_CANCELLED)),
        )

        return Response({
            "tickets": ticket_stats,
            "items": item_stats,
        })
