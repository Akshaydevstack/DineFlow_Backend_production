from django.db import models
from django.utils import timezone


class MenuItemSnapshot(models.Model):

    restaurant_id = models.CharField(
        max_length=20,
        db_index=True,
    )

    dish_id = models.CharField(
        max_length=20,
        db_index=True,
    )

    # ======================
    # CORE
    # ======================
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    # ======================
    # CATEGORY
    # ======================
    category_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
    )

    category_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    # ======================
    # PRICING
    # ======================
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    original_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )

    # ======================
    # ATTRIBUTES (AI CRITICAL)
    # ======================
    is_veg = models.BooleanField(default=False)
    is_spicy = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    is_quick_bites = models.BooleanField(default=False)

    # ======================
    # QUALITY SIGNALS
    # ======================
    average_rating = models.FloatField(default=0)
    review_count = models.IntegerField(default=0)
    total_orders = models.IntegerField(default=0)

    # ======================
    # OPERATIONS
    # ======================
    is_available = models.BooleanField(default=True)
    prep_time = models.IntegerField(null=True, blank=True)
    priority = models.IntegerField(default=0)

    # ======================
    # MEDIA
    # ======================
    image_url = models.URLField(
        null=True,
        blank=True,
    )

    # ======================
    # VERSIONING
    # ======================
    menu_version = models.CharField(
        max_length=20,
        db_index=True,
        default="v1"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("restaurant_id", "dish_id")
        indexes = [
            models.Index(fields=["restaurant_id", "dish_id"]),
            models.Index(fields=["restaurant_id", "is_available"]),
            models.Index(fields=["category_id"]),
            models.Index(fields=["is_veg"]),
            models.Index(fields=["is_popular"]),
            models.Index(fields=["is_trending"]),
            models.Index(fields=["total_orders"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.restaurant_id})"