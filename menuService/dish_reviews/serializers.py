from rest_framework import serializers 
from .models import DishReview
from dishes.models import Dish
from rest_framework import serializers
from .models import DishReview



class DishesReviewSerializer(serializers.ModelSerializer):
    dish = serializers.SlugRelatedField(
        slug_field="public_id",
        queryset=Dish.objects.all()
    )

    class Meta:
        model = DishReview
        fields = [
            "public_id",
            "restaurant_id",
            "dish",
            "user_public_id",
            "user_name",
            "user_avatar",
            "rating",
            "comment",
            "created_at",
        ]
        read_only_fields = [
            "public_id",
            "created_at",
            "user_public_id",
            "user_name",
            "restaurant_id",
        ]

    def validate(self, attrs):
        request = self.context.get("request")

        user_id = request.headers.get("X-User-Id")
        restaurant_id = request.headers.get("X-Restaurant-Id")
        dish = attrs.get("dish")

        if not restaurant_id:
            raise serializers.ValidationError("X-Restaurant-Id header is required.")

        # 🔒 Ensure dish belongs to restaurant
        if dish.restaurant_id != restaurant_id:
            raise serializers.ValidationError(
                "Dish does not belong to this restaurant."
            )

        # 🔒 Prevent duplicate review
        if DishReview.objects.filter(
            dish=dish,
            user_public_id=user_id
        ).exists():
            raise serializers.ValidationError(
                "You have already reviewed this dish."
            )

        return attrs

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError(
                "Rating must be between 1 and 5."
            )
        return value




class AdminDishReviewSerializer(serializers.ModelSerializer):
    dish_public_id = serializers.CharField(
        source="dish.public_id",
        read_only=True
    )
    dish_name = serializers.CharField(
        source="dish.name",
        read_only=True
    )

    class Meta:
        model = DishReview
        fields = [
            "public_id",
            "dish_public_id",
            "user_public_id",
            "user_name",
            "dish_name",
            "rating",
            "comment",
            "show_review",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "public_id",
            "restaurant_id",
            "dish",
            "user_public_id",
            "user_name",
            "user_avatar",
            "created_at",
            "updated_at",
            "menu_version",
        ]