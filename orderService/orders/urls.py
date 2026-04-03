# orders/urls.py
from django.urls import path
from .views import (
    OrderCreateView,
    OrderListView,
    OrderCancelView,
    OrderDetailView,
    WaiterOrderListView,
    AdminOrderListView,
    AdminOrderPaymentUpdateView,
    AdminOrderStatusUpdateView,
    AdminOrderStatsView,
    AdminHourlySalesView,
    AdminTopDishesView,
    RestaurantAdminOrderUserListView,
    AdminTableOrdersView,
    AdminTableCheckoutDetailView,
    AdminTableSessionListView,
    CloseTableSessionView,
    WaiterTableCheckoutDetailView,
    AIUserOrdersView
    )

urlpatterns = [

    path("internal/ai/create-order/", OrderCreateView.as_view(),name ="place a order by AI agent"),

    # ---------------- CUSTOMER ----------------
    
    path("internal/ai/<str:public_id>/cancel-order/", OrderCancelView.as_view(), name="cancel-order by AI agent"),
    path("internal/ai/orders/", AIUserOrdersView.as_view()),
    
    # ---------------- CUSTOMER ----------------
    path("customer/create/", OrderCreateView.as_view(), name="create-order"),
    path("customer/all-orders/", OrderListView.as_view(), name="get-all-orders"),
    path("customer/<str:public_id>/cancel/", OrderCancelView.as_view(), name="cancel-order"),
    path("customer/<str:public_id>/", OrderDetailView.as_view(), name="order-detail"),

    # ---------------- WAITER ----------------
    path("waiter/create/", OrderCreateView.as_view(), name="waiter-create-order"),
    path("waiter/all-orders/", WaiterOrderListView.as_view(), name="waiter-get-all-orders"),
    path("waiter/<str:public_id>/cancel/", OrderCancelView.as_view(), name="waiter-cancel-order"),
    path("waiter/<str:public_id>/", OrderDetailView.as_view(), name="waiter-order-detail"),
    path("waiter/table/<str:table_public_id>/checkout/",WaiterTableCheckoutDetailView.as_view()),

     # ---------------- Admin ----------------
    path("restaurant-admin/orders/", AdminOrderListView.as_view()),
    path("restaurant-admin/orders/<str:public_id>/status/", AdminOrderStatusUpdateView.as_view()),
    path("restaurant-admin/orders/<str:public_id>/payment/", AdminOrderPaymentUpdateView.as_view()),
    path("restaurant-admin/orders/order-status/", AdminOrderStatsView.as_view()),
    path("restaurant-admin/orders/hourly-sales/",AdminHourlySalesView.as_view()),
    path("restaurant-admin/orders/top-dishes/",AdminTopDishesView.as_view()),
    path("restaurant-admin/customer/<str:user_id>/", RestaurantAdminOrderUserListView.as_view()),
    path("restaurant-admin/table/<str:table_public_id>/orders/",AdminTableOrdersView.as_view()),
    path("restaurant-admin/table/<str:table_public_id>/checkout/",AdminTableCheckoutDetailView.as_view()),
    path("restaurant-admin/table-sessions/", AdminTableSessionListView.as_view(), name="admin-table-sessions",),
    path("restaurant-admin/table-sessions/<str:session_public_id>/close/",CloseTableSessionView.as_view(),)
]   
