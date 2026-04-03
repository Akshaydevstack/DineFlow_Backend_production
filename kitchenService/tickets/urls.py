from django.urls import path
from .views import (
    KitchenTicketListView,
    KitchenTicketDetailView,
    KitchenTicketStatusUpdateView,
    KitchenItemStatusUpdateView,
    AdminKitchenTicketListView,
    AdminKitchenTicketStatusUpdateView,
    AdminKitchenItemStatusUpdateView,
    AdminKitchenDashboardStatsView
)

urlpatterns = [
    # -----------------------------------
    # Kitchen Staff APIs
    # -----------------------------------
    path(
        "kitchen-staff/tickets/",
        KitchenTicketListView.as_view(),name= "To see the kitchen tickets"
    ),
    path(
        "kitchen-staff/tickets/<str:public_id>/",
        KitchenTicketDetailView.as_view()
    ),
    path(
        "kitchen-staff/tickets/<str:public_id>/status/",
        KitchenTicketStatusUpdateView.as_view()
    ),
    path(
        "kitchen-staff/items/<int:item_id>/status/",
        KitchenItemStatusUpdateView.as_view()
    ),

    # -----------------------------------
    # Restaurant Admin APIs
    # -----------------------------------
    path(
        "restaurant-admin/tickets/",
        AdminKitchenTicketListView.as_view()
    ),
    path(
        "restaurant-admin/tickets/<str:public_id>/status/",
        AdminKitchenTicketStatusUpdateView.as_view()
    ),
    path(
        "restaurant-admin/items/<int:item_id>/status/",
        AdminKitchenItemStatusUpdateView.as_view()
    ),
    path(
    "restaurant-admin/tickets/tickest-stats/",
    AdminKitchenDashboardStatsView.as_view()
),
]
