import uuid
from django.db import models, transaction
from categories.models import Category
from utils.id_generator import generate_unique_id
from kafka.producer import publish_menu_item_event


class Dish(models.Model):
    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )

    restaurant_id = models.CharField(
        max_length=20,
        db_index=True,
        editable=False
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="dishes",
    )

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    price = models.DecimalField(max_digits=8, decimal_places=2)

    original_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    prep_time = models.PositiveIntegerField(
        help_text="Estimated time in minutes")

    is_spicy = models.BooleanField(default=False)
    is_veg = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    is_quick_bites = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    total_orders = models.PositiveIntegerField(default=0)

    average_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.0)
    
    review_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    menu_version = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"],
                name="uniq_dish_per_category"
            )
        ]
        indexes = [
            models.Index(fields=["restaurant_id", "is_available"]),
            models.Index(fields=["category", "is_available"]),
            models.Index(fields=["is_veg", "is_available"]),
            models.Index(fields=["is_popular"]),
            models.Index(fields=["is_trending"]),
            models.Index(fields=["is_quick_bites"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["total_orders"]),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if not self.public_id:
            self.public_id = generate_unique_id("DISH")

        if not self.restaurant_id:
            raise ValueError("restaurant_id is required")

        if is_new:
            self.menu_version = "v1"
        else:
            old_version = (
                Dish.objects
                .filter(pk=self.pk)
                .values_list("menu_version", flat=True)
                .first()
            )

            if old_version:
                version = int(old_version.lstrip("v"))
                self.menu_version = f"v{version + 1}"
            else:
                self.menu_version = "v1"

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        dish_data = {
            "dish_id": self.public_id,
            "restaurant_id": self.restaurant_id,
            "menu_version": self.menu_version,
        }

        super().delete(*args, **kwargs)

        transaction.on_commit(
            lambda: publish_menu_item_event("DELETED", dish_data)
        )


class DishImage(models.Model):
    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )

    dish = models.ForeignKey(
        Dish,
        on_delete=models.CASCADE,
        related_name="images",
    )

    image_url = models.URLField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dish", "image_url"],
                name="uniq_dish_image"
            )
        ]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("IMG")

        super().save(*args, **kwargs)
