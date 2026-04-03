from django.db import models,transaction
from django.utils import timezone
from utils.id_generator import generate_unique_id
from dishes.models import Dish
from django.db.models import Avg,Count

class DishReview(models.Model):
    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )
    
    restaurant_id = models.CharField(
    max_length=20,
    db_index=True,
    )

    dish = models.ForeignKey(
        Dish,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    
    user_public_id = models.CharField(max_length=20)
    user_name = models.CharField(max_length=100)
    user_avatar = models.URLField(blank=True, null=True)

    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)

    show_review = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    menu_version = models.CharField(
    max_length=20,
    db_index=True,
    default="v1"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dish", "user_public_id"],
                name="uniq_review_per_user_per_dish"
            )
        ]
        indexes = [
            models.Index(
                fields=["dish"],
                name="idx_review_dish"
            ),
            models.Index(
                fields=["user_public_id"],
                name="idx_review_user"
            ),
            models.Index(
                fields=["dish", "-created_at"],
                name="idx_review_recent"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("REV")

        with transaction.atomic():
            super().save(*args, **kwargs)
            self._sync_dish_rating()

    def delete(self, *args, **kwargs):
        dish = self.dish

        with transaction.atomic():
            super().delete(*args, **kwargs)
            self._sync_dish_rating(dish)

    def _sync_dish_rating(self, dish=None):
        dish = dish or self.dish

        stats = dish.reviews.aggregate(
            avg_rating=Avg("rating"),
            total_reviews=Count("id")
        )

        dish.average_rating = round(stats["avg_rating"] or 0, 2)
        dish.review_count = stats["total_reviews"] or 0

        # Increment version
        old_version = dish.menu_version or "v1"
        version = int(old_version.lstrip("v"))
        dish.menu_version = f"v{version + 1}"

        dish.save(update_fields=[
            "average_rating",
            "review_count",
            "menu_version"
        ])
    def __str__(self):
        return f"{self.user_name} → {self.dish.name}"