from rest_framework import serializers 
from .models import Category
from django.db import IntegrityError

class CategoryListSerializer(serializers .ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "public_id",
            "name",
            "image",
            "is_active"
        ]
    
class CategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "public_id",
            "name",
            "image",
            "is_active",
        ]
        read_only_fields = ["public_id"]

    def create(self, validated_data):
        request = self.context["request"]

        restaurant_id = request.headers.get("X-Restaurant-Id")
        if not restaurant_id:
            raise serializers.ValidationError({
                "restaurant_id": "Restaurant ID header is required"
            })

        validated_data["restaurant_id"] = restaurant_id

        try:
            category = Category.objects.create(**validated_data)
        except IntegrityError:
            raise serializers.ValidationError({
                "name": "Category with this name already exists"
            })

        return category