from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from common.tenant import get_tenant_context
from .serializers import AddItemSerializer, UpdateQuantitySerializer
from .services import get_cart, save_cart, validate_dish, build_cart_response, clear_cart
from cart.models import MenuItemSnapshot


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


# ==============
# Internal API
# ===============

class AICartItemsView(APIView):

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        restaurant_id, user_id = get_tenant_context(request)
        if not restaurant_id or not user_id:
            return Response(
                {"error": "Missing tenant context"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart = get_cart(restaurant_id, user_id)

        # Early return — no cart, no DB query needed
        if not cart:
            return Response([], status=status.HTTP_200_OK)

        # Single batch query — never N+1
        dish_ids = list(cart.keys())
        snapshots = MenuItemSnapshot.objects.filter(
            restaurant_id=restaurant_id,
            dish_id__in=dish_ids,
        )
        snapshot_map = {s.dish_id: s for s in snapshots}

        items = []
        for dish_id, item in cart.items():
            snapshot = snapshot_map.get(dish_id)
            if not snapshot:
                continue
            items.append({
                # Core
                "dish_id":        dish_id,
                "name":           snapshot.name,
                "description":    snapshot.description,
                "category_name":  snapshot.category_name,
                "price": snapshot.price,
                "original_price" :snapshot.original_price,
                # Attributes
                "is_veg":         snapshot.is_veg,
                "is_spicy":       snapshot.is_spicy,
                "is_popular":     snapshot.is_popular,
                "is_trending":    snapshot.is_trending,
                "is_quick_bites": snapshot.is_quick_bites,
                # Quality signals
                "average_rating": snapshot.average_rating,
                "total_orders":   snapshot.total_orders,
                "image":  snapshot.image_url,
                # Context
                "quantity":       item.get("quantity", 1),
            })

        return Response(items, status=status.HTTP_200_OK)


# Agent tools API  add to cart

class AICartItemsViewForAgent(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        restaurant_id, user_id = get_tenant_context(request)
        cart = get_cart(restaurant_id, user_id)
        cart_response = build_cart_response(cart)

        return Response(cart_response, status=status.HTTP_200_OK)



class AICartAddItemView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        restaurant_id, user_id = get_tenant_context(request)

        dish_id = request.data.get("dish_id")
        quantity = int(request.data.get("quantity", 1))

        if not dish_id:
            return Response(
                {"error": "dish_id required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            dish = MenuItemSnapshot.objects.get(
                restaurant_id=restaurant_id,
                dish_id=dish_id,
                is_available=True
            )
        except MenuItemSnapshot.DoesNotExist:
            return Response(
                {"error": "Dish not available"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart = get_cart(restaurant_id, user_id)

        if dish_id in cart:
            cart[dish_id]["quantity"] += quantity
        else:
            cart[dish_id] = {
                "name": dish.name,
                "price": str(dish.price),
                # Added so build_cart_response can calculate discounts!
                "original_price": str(dish.original_price),
                "quantity": quantity,
                "image": dish.image_url,
            }

        save_cart(restaurant_id, user_id, cart)

        # Using build_cart_response to get rich data!
        return Response({
            "status": "added",
            **build_cart_response(cart)
        }, status=status.HTTP_200_OK)


class AICartUpdateItemView(APIView):
    authentication_classes = []
    permission_classes = []

    def patch(self, request):
        restaurant_id, user_id = get_tenant_context(request)

        dish_id = request.data.get("dish_id")
        quantity = int(request.data.get("quantity", 1))

        cart = get_cart(restaurant_id, user_id)

        if dish_id not in cart:
            return Response(
                {"error": "Item not in cart"},
                status=status.HTTP_404_NOT_FOUND
            )

        if quantity <= 0:
            del cart[dish_id]
        else:
            cart[dish_id]["quantity"] = quantity

        save_cart(restaurant_id, user_id, cart)

        return Response({
            "status": "updated",
            **build_cart_response(cart)
        }, status=status.HTTP_200_OK)


class AICartRemoveItemView(APIView):
    authentication_classes = []
    permission_classes = []

    def delete(self, request):
        restaurant_id, user_id = get_tenant_context(request)
        dish_id = request.data.get("dish_id")

        cart = get_cart(restaurant_id, user_id)

        if dish_id in cart:
            del cart[dish_id]
            save_cart(restaurant_id, user_id, cart)

        return Response({
            "status": "removed",
            **build_cart_response(cart)
        }, status=status.HTTP_200_OK)


class AICartClearView(APIView):
    authentication_classes = []
    permission_classes = []

    def delete(self, request):
        restaurant_id, user_id = get_tenant_context(request)

        clear_cart(restaurant_id, user_id)

        return Response({
            "status": "cleared",
            "items": [],
            "subtotal": "0.00",
            "original_subtotal": "0.00",
            "total_discount": "0.00",
            "cart_discount_percentage": "0"
        }, status=status.HTTP_200_OK)


# =================
# REST cart API
# =================


class CartView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        restaurant_id, user_id = get_tenant_context(request)
        cart = get_cart(restaurant_id, user_id)
        return Response(build_cart_response(cart), status=status.HTTP_200_OK)

    def delete(self, request):
        restaurant_id, user_id = get_tenant_context(request)

        clear_cart(restaurant_id, user_id)

        return Response(
            {
                "items": [],
                "subtotal": 0,
                "tax": 0,
                "grand_total": 0
            },
            status=status.HTTP_200_OK
        )


class AddItemView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        restaurant_id, user_id = get_tenant_context(request)

        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dish_id = serializer.validated_data["dish_id"]
        quantity = serializer.validated_data["quantity"]

        try:
            dish = MenuItemSnapshot.objects.get(
                restaurant_id=restaurant_id,
                dish_id=dish_id,
                is_available=True,
            )
        except MenuItemSnapshot.DoesNotExist:
            return Response(
                {"error": "Dish not available"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart = get_cart(restaurant_id, user_id)

        if dish_id in cart:
            cart[dish_id]["quantity"] += quantity
        else:
            cart[dish_id] = {
                "name": dish.name,
                "price": str(dish.price),
                "original_price": str(dish.original_price),
                "quantity": quantity,
                "image": dish.image_url
            }

        save_cart(restaurant_id, user_id, cart)
        return Response(build_cart_response(cart), status=status.HTTP_200_OK)


class RemoveItemView(APIView):
    authentication_classes = []
    permission_classes = []

    def delete(self, request, dish_id):
        restaurant_id, user_id = get_tenant_context(request)

        cart = get_cart(restaurant_id, user_id)

        if dish_id not in cart:
            return Response(
                {"error": "Item not found in cart"},
                status=status.HTTP_404_NOT_FOUND
            )

        del cart[dish_id]

        save_cart(restaurant_id, user_id, cart)

        return Response(
            build_cart_response(cart),
            status=status.HTTP_200_OK
        )


class UpdateItemView(APIView):
    authentication_classes = []
    permission_classes = []

    def patch(self, request, dish_id):
        restaurant_id, user_id = get_tenant_context(request)

        serializer = UpdateQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data["quantity"]

        cart = get_cart(restaurant_id, user_id)

        if dish_id not in cart:
            return Response(
                {"error": "Item not found in cart"},
                status=status.HTTP_404_NOT_FOUND
            )

        if quantity == 0:
            del cart[dish_id]
        else:
            cart[dish_id]["quantity"] = quantity

        save_cart(restaurant_id, user_id, cart)

        return Response(
            build_cart_response(cart),
            status=status.HTTP_200_OK
        )


# ===================
# RestaurantAdmin
# ===================

class RestaurantAdminUserCartView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, user_id):
        restaurant_id, _ = get_tenant_context(request)

        if not restaurant_id:
            return Response(
                {"error": "Restaurant ID required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart = get_cart(restaurant_id, user_id)

        return Response(
            {
                "restaurant_id": restaurant_id,
                "user_id": user_id,
                **build_cart_response(cart)
            },
            status=status.HTTP_200_OK
        )
