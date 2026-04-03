from django.db import models
from django.utils import timezone
from utils.id_generator import generate_unique_id

class Category(models.Model):
    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )

    restaurant_id = models.CharField(
    max_length=20,
    db_index=True,
    )
    
    name = models.CharField(max_length=100)
    image = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    menu_version = models.CharField(
    max_length=20,
    db_index=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="uniq_category_name"
            )
        ]
        indexes = [
            models.Index(
                fields=["is_active"],
                name="idx_category_active"
            ),
            models.Index(
                fields=["name"],
                name="idx_category_name"
            ),
        ]

    def save(self, *args, **kwargs):

        is_new = self.pk is None

        if not self.public_id:
            self.public_id = generate_unique_id("CAT")
        

        if is_new:
            self.menu_version = "v1"
        else:

            try:
                old_instance = Category.objects.get(pk=self.pk)
                old_version_str = old_instance.menu_version

                if old_version_str.startswith('v'):
                    version_num = int(old_version_str[1:])
                    self.menu_version = f"v{version_num + 1}"
                else:
                    self.menu_version = "v1"
            except (Category.DoesNotExist, ValueError):
                self.menu_version = "v1"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name