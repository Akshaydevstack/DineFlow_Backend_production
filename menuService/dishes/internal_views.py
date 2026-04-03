# dishes/internal_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from dishes.models import Dish

8
class InternalDishDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, public_id):

        if request.headers.get("X-Internal-Call") != "true":
            return Response({"error": "Forbidden"}, status=403)

        restaurant_id = request.headers.get("X-Restaurant-Id")

        if not restaurant_id:
            return Response(
                {"error": "Missing restaurant context"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            dish = Dish.objects.get(
                public_id=public_id,
                is_available=True
            )
        except Dish.DoesNotExist:
            return Response(
                {"error": "Dish not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "public_id": dish.public_id,
            "name": dish.name,
            "price": float(dish.price),
        }, status=status.HTTP_200_OK)



class InternalDishBatchView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if request.headers.get("X-Internal-Call") != "true":
            return Response(
                {"error": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN
            )

        restaurant_id = request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            return Response(
                {"error": "Missing restaurant context"},
                status=status.HTTP_400_BAD_REQUEST
            )

        dish_ids = request.data.get("dish_ids")
        if not dish_ids or not isinstance(dish_ids, list):
            return Response(
                {"error": "dish_ids must be a list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        dishes = Dish.objects.filter(
            public_id__in=dish_ids,
            is_available=True
        )

        if dishes.count() != len(set(dish_ids)):
            return Response(
                {"error": "One or more dishes not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        data = [
            {
                "dish_id": dish.public_id,
                "name": dish.name,
                "price": str(dish.price),
            }
            for dish in dishes
        ]

        return Response(data, status=status.HTTP_200_OK)