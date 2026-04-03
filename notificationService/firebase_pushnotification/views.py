from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import DeviceToken, Notification
from django.db import transaction
from .serializers import NotificationSerializer, BroadcastNotificationListSerializer, RestaurantAdminBroadcastNotificationSerializer
from .services.fcm_service import send_restaurant_broadcast_notification_task
import uuid
from django.db.models import Q

class HealthCheckView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class RegisterDeviceView(APIView):
    def post(self, request):
        user_id = request.headers.get("X-User-Id")
        role = request.headers.get("X-User-Role")
        restaurant_id = request.headers.get("X-Restaurant-Id")

        fcm_token = request.data.get("fcm_token")
        device_type = request.data.get("device_type", "web")

        if not user_id or not role or not fcm_token:
            return Response(
                {"error": "Missing required data"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():

            device, created = DeviceToken.objects.update_or_create(
                fcm_token=fcm_token,
                defaults={
                    "user_id": user_id,
                    "role": role,
                    "restaurant_id": restaurant_id,
                    "device_type": device_type,
                    "is_active": True,
                }
            )

            DeviceToken.objects.filter(
                user_id=user_id
            ).exclude(
                fcm_token=fcm_token
            ).update(is_active=False)

        return Response(
            {
                "status": "Token registered",
                "created": created
            },
            status=status.HTTP_200_OK
        )


class NotificationListView(APIView):

    def get(self, request):
        user_id = request.headers.get("X-User-Id")

        notifications = Notification.objects.filter(
            user_id=user_id
        ).order_by("-created_at")

        serializer = NotificationSerializer(
            notifications,
            many=True
        )

        return Response(serializer.data)


class MarkNotificationReadView(APIView):

    def patch(self, request, pk):
        user_id = request.headers.get("X-User-Id")
        Notification.objects.filter(
            id=pk,
            user_id=user_id
        ).update(is_read=True)

        return Response({"message": "Marked as read"})


# For sending notification to all the users


class RestaurantAdminBroadcastNotificationView(APIView):

    # ------------------------
    # LIST BROADCAST
    # ------------------------
        
    def get(self, request):

        search = request.GET.get("search")

        queryset = Notification.objects.filter(
            is_broadcast=True,
            is_show=True,
            topic="broadcast"
        )

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(body__icontains=search)  |
                Q(reference_id__icontains=search)
            )

        notifications = (
            queryset
            .values(
                "reference_id",
                "title",
                "body",
                "created_at"
            )
            .order_by("reference_id", "-created_at")
            .distinct("reference_id")
        )

        serializer = BroadcastNotificationListSerializer(
            notifications,
            many=True
        )

        return Response(serializer.data)

    # ------------------------
    # CREATE BROADCAST
    # ------------------------
    def post(self, request):

        serializer = RestaurantAdminBroadcastNotificationSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        restaurant_id = request.headers.get("X-Restaurant-Id")

        title = serializer.validated_data["title"]
        body = serializer.validated_data["body"]
        role = serializer.validated_data.get("role")

        queryset = DeviceToken.objects.filter(
            restaurant_id=restaurant_id,
            is_active=True
        )

        if role:
            queryset = queryset.filter(role=role)

        user_ids = queryset.values_list(
            "user_id",
            flat=True
        ).distinct()

        reference_id = f"broadcast_{uuid.uuid4().hex[:12]}"

        notifications = [
            Notification(
                user_id=user_id,
                title=title,
                body=body,
                reference_id = reference_id,
                topic="broadcast",
                is_broadcast=True,
                is_show=True
            )
            for user_id in user_ids
        ]

        Notification.objects.bulk_create(notifications)

        send_restaurant_broadcast_notification_task.delay(
            restaurant_id=restaurant_id,
            title=title,
            body=body,
            role=role
        )

        return Response(
            {
                "status": "Broadcast created",
                "reference_id": reference_id,
                "users": len(user_ids)
            },
            status=status.HTTP_201_CREATED
        )


class RestaurantAdminBroadcastNotificationDetailView(APIView):

    # ------------------------
    # UPDATE BROADCAST
    # ------------------------
    def patch(self, request, reference_id):

        title = request.data.get("title")
        body = request.data.get("body")

        update_data = {}

        if title:
            update_data["title"] = title

        if body:
            update_data["body"] = body

        Notification.objects.filter(
            reference_id=reference_id,
            is_broadcast=True
        ).update(**update_data)

        return Response({
            "status": "Broadcast updated"
        })

    # ------------------------
    # DELETE BROADCAST
    # ------------------------
    def delete(self, request, reference_id):

        Notification.objects.filter(
            reference_id=reference_id,
            is_broadcast=True
        ).update(is_show=False)

        return Response({
            "status": "Broadcast deleted"
        })
