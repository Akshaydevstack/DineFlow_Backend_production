from django.db import models
from django.utils import timezone
from django.conf import settings
from utils.ids import generate_unique_id
import uuid
from datetime import timedelta
from django.conf import settings
from django.utils.text import slugify

# ==========================================
# 🔹 RESTAURANT MODEL
# ==========================================

class Restaurant(models.Model):
    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True
    )

    name = models.CharField(max_length=255)

    slug = models.SlugField(max_length=300, unique=True, null=True, blank=True)

    address = models.TextField()
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)

    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    phone = models.CharField(max_length=15)
    email = models.EmailField(null=True, blank=True)

    is_open = models.BooleanField(default=True)
    opening_time = models.TimeField()
    closing_time = models.TimeField()

    gst_number = models.CharField(max_length=20, null=True, blank=True)
    fssai_license = models.CharField(max_length=50, null=True, blank=True)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.0
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    restaurant_version = models.CharField(max_length=10, default="v1")

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "is_open"]),
            models.Index(fields=["city", "is_active"]),
        ]

    
    def save(self, *args, **kwargs):

        # generate public_id
        if not self.public_id:
            self.public_id = generate_unique_id("rest")

        # generate slug automatically
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Restaurant.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.city})"


# ==========================================
# 🔹 ZONES (Indoor, Outdoor, AC)
# ==========================================

class RestaurantZone(models.Model):
    public_id = models.CharField(max_length=20, unique=True, editable=False)

    zone_version = models.CharField(max_length=10, default="v1")

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="zones"
    )
    name = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("zone")
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ["restaurant", "name"]

    def __str__(self):
        return f"{self.name} - {self.restaurant.name}"




# ==========================================
# 🔹 TABLES (QR Codes)
# ==========================================

class Table(models.Model):
    TYPE_CHOICES = (
        ("standard", "Standard Table"),
        ("counter", "Counter / Takeaway"),
        ("delivery", "Delivery Placeholder"),
    )

    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True
    )

    restaurant = models.ForeignKey(
        'Restaurant',
        on_delete=models.CASCADE,
        related_name="tables",
        db_index=True
    )

    zone = models.ForeignKey(
        'RestaurantZone',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tables"
    )

    table_number = models.CharField(max_length=50)

    capacity = models.PositiveIntegerField(default=2)

    qr_code_token = models.UUIDField(default=uuid.uuid4, editable=False)

    table_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="standard"
    )

    is_occupied = models.BooleanField(default=False)
    occupied_by_user_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
    )

    is_reserved_manual = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    table_version = models.CharField(max_length=10, default="v1")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "table_number"],
                name="unique_table_number_per_restaurant"
            )
        ]
        indexes = [
            models.Index(fields=["restaurant", "is_active"]),
            models.Index(fields=["table_type"]),
            models.Index(fields=["restaurant", "zone"])
        ]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("tbl")
        else:
            old = Table.objects.filter(pk=self.pk).first()
            if old:
                current_version = int(old.table_version.lstrip("v"))
                self.table_version = f"v{current_version + 1}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"T-{self.table_number} ({self.restaurant.name})"

    @property
    def qr_url(self):
        base_url = getattr(settings, "FRONTEND_URL",
                           "https://dineflow.store/customer")
        return f"{base_url}/scan/{self.restaurant.public_id}/{self.public_id}/{self.qr_code_token}/{self.zone.public_id}/{self.table_number}/{self.restaurant.name}"





class Reservation(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending Confirmation"),
        ("confirmed", "Confirmed"),
        ("seated", "Seated (Active)"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
    )

    public_id = models.CharField(max_length=20, unique=True, editable=False)

    restaurant = models.ForeignKey(
        'Restaurant', on_delete=models.CASCADE, related_name="reservations"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations"
    )

    table = models.ForeignKey(
        Table,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations"
    )

    reservation_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=90)

    end_time = models.DateTimeField(editable=False)

    guest_count = models.PositiveIntegerField(default=2)
    special_request = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    reservation_version = models.CharField(max_length=10, default="v1")

    class Meta:
        indexes = [
            models.Index(fields=["restaurant", "reservation_time"]),
            models.Index(fields=["table", "reservation_time"]),
        ]
        ordering = ["-reservation_time"]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("res")

        if self.reservation_time:
            self.end_time = self.reservation_time + \
                timedelta(minutes=self.duration_minutes)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.reservation_time}"
