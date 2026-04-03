from django.urls import path
from .views import CartView, AddItemView,RemoveItemView,UpdateItemView,RestaurantAdminUserCartView,AICartItemsView
from .views import AICartAddItemView,AICartUpdateItemView,AICartRemoveItemView,AICartClearView,AICartItemsViewForAgent

urlpatterns = [
    # Internal API
    path("internal/ai/items/", AICartItemsView.as_view()),

  # For agent

    path("internal/ai/list-items/", AICartItemsViewForAgent.as_view(),name="List the item for AI"),
    path("internal/ai/add/", AICartAddItemView.as_view()),
    path("internal/ai/update/", AICartUpdateItemView.as_view()),
    path("internal/ai/remove/", AICartRemoveItemView.as_view()),
    path("internal/ai/clear/", AICartClearView.as_view()),


    # Customer API
    path("customer/", CartView.as_view(), name="cart-detail or clear cart"),
    path("customer/add-items/", AddItemView.as_view(), name="cart-add-item"),
    path("customer/remove-item/<str:dish_id>/", RemoveItemView.as_view(), name="cart-remove-item"),
    path("customer/update-item/<str:dish_id>/", UpdateItemView.as_view(), name="cart-update-item"),

     # Waiter routes (same views reused)
    path("waiter/", CartView.as_view()),
    path("waiter/add-items/", AddItemView.as_view()),
    path("waiter/remove-item/<str:dish_id>/", RemoveItemView.as_view()),
    path("waiter/update-item/<str:dish_id>/", UpdateItemView.as_view()),

    # Admin routes (same views reused)
      path("restaurant-admin/<str:user_id>/", RestaurantAdminUserCartView.as_view(),name="List all items in the cart"),
]