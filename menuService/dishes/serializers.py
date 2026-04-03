from rest_framework import serializers
from .models import Dish, DishImage
from utils.id_generator import generate_unique_id
from django.db import IntegrityError
from kafka.producer import publish_menu_item_event
from django.db import transaction
from categories.models import Category
from dish_reviews.serializers import DishesReviewSerializer
# for listing all the details of a dish for user


class DishReadSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    category_name = serializers.CharField(
        source="category.name", read_only=True
    )

    category = serializers.CharField(
        source="category.public_id", read_only=True
    )

    class Meta:
        model = Dish
        fields = [

            "public_id",
            "restaurant_id",
            "category",
            "category_name",
            "name",
            "description",
            "price",
            "original_price",
            "prep_time",
            "is_veg",
            "is_spicy",
            "is_popular",
            "is_quick_bites",
            "is_trending",
            "is_available",
            "priority",
            "total_orders",
            "average_rating",
            "review_count",
            "images",
            "reviews",
            "created_at",
            "updated_at",
        ]

    def get_images(self, obj):
        return [img.image_url for img in obj.images.all()]

    def get_reviews(self, obj):
        reviews = obj.reviews.order_by("-created_at")[:5]
        return DishesReviewSerializer(reviews, many=True).data


# Admin create Serializer

class DishWriteSerializer(serializers.ModelSerializer):
    images = serializers.ListField(
        child=serializers.URLField(),
        write_only=True,
        required=False
    )

    category = serializers.SlugRelatedField(
        slug_field="public_id",
        queryset=Category.objects.all()
    )

    class Meta:
        model = Dish
        fields = [
            "public_id",
            "restaurant_id",
            "category",
            "name",
            "description",
            "price",
            "original_price",
            "prep_time",
            "is_veg",
            "is_spicy",
            "is_popular",
            "is_quick_bites",
            "is_trending",
            "priority",
            "is_available",
            "images",
        ]
        read_only_fields = ("public_id",)

    def validate_category(self, value):
        restaurant_id = self.context["request"].headers.get("X-Restaurant-Id")
        if value.restaurant_id != restaurant_id:
            raise serializers.ValidationError(
                "Category does not belong to this restaurant")
        return value

    def create(self, validated_data):
        images = validated_data.pop("images", [])

        with transaction.atomic():
            try:
                dish = Dish.objects.create(**validated_data)
            except IntegrityError:
                raise serializers.ValidationError({
                    "name": "Dish with this name already exists in this category"
                })

            DishImage.objects.bulk_create([
                DishImage(
                    public_id=generate_unique_id("IMG"),
                    dish=dish,
                    image_url=url
                )
                for url in images
            ])

            # ✅ Publish CREATED only if first image exists
            if images:
                first_image = images[0]

                transaction.on_commit(
                    lambda: publish_menu_item_event(
                        "CREATED",
                        {
                            "dish_id": dish.public_id,
                            "restaurant_id": dish.restaurant_id,

                            # ✅ CORE
                            "name": dish.name,
                            "description": dish.description,

                            # ✅ CATEGORY
                            "category_id": dish.category.public_id,
                            "category_name": dish.category.name,

                            # ✅ PRICE
                            "price": str(dish.price),
                            "original_price": str(dish.original_price) if dish.original_price else None,

                            # ✅ ATTRIBUTES (AI CRITICAL)
                            "is_veg": dish.is_veg,
                            "is_spicy": dish.is_spicy,
                            "is_popular": dish.is_popular,
                            "is_trending": dish.is_trending,
                            "is_quick_bites": dish.is_quick_bites,

                            # ✅ QUALITY SIGNALS
                            "average_rating": float(dish.average_rating),
                            "review_count": dish.review_count,
                            "total_orders": dish.total_orders,

                            # ✅ OPS
                            "is_available": dish.is_available,
                            "prep_time": dish.prep_time,
                            "priority": dish.priority,

                            # ✅ MEDIA
                            "image_url": first_image,

                            # ✅ VERSIONING
                            "menu_version": dish.menu_version,
                            "occurred_at": dish.created_at.isoformat(),
                        },
                    )
                )

        return dish


    def update(self, instance, validated_data):
        images = validated_data.pop("images", None)

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            instance.save()

            image_url = None

            if images is not None:
                instance.images.all().delete()

                DishImage.objects.bulk_create([
                    DishImage(
                        public_id=generate_unique_id("IMG"),
                        dish=instance,
                        image_url=url
                    )
                    for url in images
                ])

                if images:
                    image_url = images[0]
            else:
                first_image = instance.images.first()
                if first_image:
                    image_url = first_image.image_url

            transaction.on_commit(
                lambda: publish_menu_item_event(
                    "UPDATED",
                    {
                        "dish_id": instance.public_id,
                        "restaurant_id": instance.restaurant_id,

                        # CORE
                        "name": instance.name,
                        "description": instance.description,

                        # CATEGORY
                        "category_id": instance.category.public_id,
                        "category_name": instance.category.name,

                        # PRICE
                        "price": str(instance.price),
                        "original_price": str(instance.original_price) if instance.original_price else None,

                        # ATTRIBUTES
                        "is_veg": instance.is_veg,
                        "is_spicy": instance.is_spicy,
                        "is_popular": instance.is_popular,
                        "is_trending": instance.is_trending,
                        "is_quick_bites": instance.is_quick_bites,

                        # QUALITY
                        "average_rating": float(instance.average_rating),
                        "review_count": instance.review_count,
                        "total_orders": instance.total_orders,

                        # OPS
                        "is_available": instance.is_available,
                        "prep_time": instance.prep_time,
                        "priority": instance.priority,

                        # MEDIA
                        "image_url": image_url,

                        # VERSION
                        "menu_version": instance.menu_version,
                        "occurred_at": instance.updated_at.isoformat(),
                    },
                )
            )

        return instance
