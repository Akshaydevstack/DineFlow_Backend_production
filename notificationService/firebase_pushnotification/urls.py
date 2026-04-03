from django.urls import path
from .views import (RegisterDeviceView, NotificationListView, MarkNotificationReadView,
                    RestaurantAdminBroadcastNotificationDetailView, RestaurantAdminBroadcastNotificationView)
urlpatterns = [
    path('customer/firebase-fcm/register-device/',
         RegisterDeviceView.as_view(), name='register_device of user'),
    path("customer/", NotificationListView.as_view()),
    path("customer/<int:pk>/read/", MarkNotificationReadView.as_view()),
    path(
        "restaurant-admin/notifications/broadcast/",
        RestaurantAdminBroadcastNotificationView.as_view()
    ),

    path(
        "restaurant-admin/notifications/broadcast/<str:reference_id>/",
        RestaurantAdminBroadcastNotificationDetailView.as_view()
    ),
]
