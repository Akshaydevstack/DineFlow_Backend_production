from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from utils.id_generator import generate_unique_id
from orders.kafka.producer import publish_session_closed
from decimal import Decimal
from django.db import transaction


class TableSnapshot(models.Model):
    restaurant_id = models.CharField(max_length=20, db_index=True)
    restaurant_name = models.CharField(max_length=20, db_index=True)

    table_public_id = models.CharField(max_length=20, db_index=True)
    table_number = models.CharField(max_length=50)

    zone_public_id = models.CharField(max_length=20)
    zone_name = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    table_version = models.CharField(max_length=10, default="v1")

    class Meta:
        unique_together = ("restaurant_id", "table_public_id")



class TableSession(models.Model):

    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )

    restaurant_id = models.CharField(
        max_length=20,
        db_index=True,
    )

    table_public_id = models.CharField(
        max_length=20,
        db_index=True,
    )

    table_number = models.CharField(max_length=50)

    zone_public_id = models.CharField(max_length=20)
    zone_name = models.CharField(max_length=100)

    STATUS_ACTIVE = "ACTIVE"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    started_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    session_version = models.CharField(max_length=10, default="v1")

    class Meta:
        indexes = [
            models.Index(fields=["restaurant_id", "table_public_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant_id", "table_public_id"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_session_per_table",
            )
        ]

    def save(self, *args, **kwargs):

        if not self.public_id:
            self.public_id = generate_unique_id("SES")
        else:
            old = TableSession.objects.filter(pk=self.pk).first()
            if old:
                current_version = int(old.session_version.lstrip("v"))
                self.session_version = f"v{current_version + 1}"

        super().save(*args, **kwargs)





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




class Order(models.Model):

    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )

    user_id = models.CharField(
        max_length=20,
        editable=False,)

    restaurant_id = models.CharField(
        max_length=20,
        db_index=True
    )

    session = models.ForeignKey(
        TableSession,
        related_name="orders",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    STATUS_CREATED = "CREATED"
    STATUS_PAID = "PAID"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_PREPARING = "PREPARING"
    STATUS_READY = "READY"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = (
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_READY, "Ready"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED,
        db_index=True,
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    tax = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    currency = models.CharField(
        max_length=3,
        default="INR",
    )

    PAYMENT_PENDING = "PENDING"
    PAYMENT_PAID = "PAID"
    PAYMENT_FAILED = "FAILED"

    PAYMENT_STATUS_CHOICES = (
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_FAILED, "Failed"),
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
        db_index=True,
    )

    payment_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    paid_at = models.DateTimeField(null=True, blank=True)

    special_request = models.TextField(blank=True, null=True , max_length=500)

    created_at = models.DateTimeField(default=timezone.now)

    updated_at = models.DateTimeField(auto_now=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    table_number = models.CharField(null=True, blank=True)
    
    table_public_id = models.CharField(
        max_length=20, null=True, blank=True, db_index=True)

    zone_name = models.CharField(null=True, blank=False)
    zone_public_id = models.CharField(
        max_length=20, null=True, blank=True, db_index=True)

    waiter_id = models.CharField(null=True, blank=True)
    waiter_name = models.CharField(null=True, blank=True)

    order_by = models.CharField(default="customer")

    accepted_at = models.DateTimeField(null=True, blank=True)

    preparing_at = models.DateTimeField(null=True, blank=True)

    ready_at = models.DateTimeField(null=True, blank=True)

    order_version = models.CharField(max_length=10, default="v1")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("ORD")
        super().save(*args, **kwargs)

    def calculate_tax(self):
        TAX_RATE = Decimal("0.05")
        return (self.subtotal * TAX_RATE).quantize(Decimal("0.01"))

    def recalculate_totals(self):
        subtotal = sum(item.total_price for item in self.items.all())

        self.subtotal = subtotal
        self.tax = self.calculate_tax()
        self.total = subtotal + self.tax - self.discount
        self.save(update_fields=["subtotal", "tax", "total"])

    def update_status(self, new_status, occurred_at=None):

        allowed = {
            self.STATUS_CREATED: [
                self.STATUS_ACCEPTED,
                self.STATUS_CANCELLED,
            ],
            self.STATUS_ACCEPTED: [
                self.STATUS_PREPARING,
                self.STATUS_CANCELLED,
            ],
            self.STATUS_PREPARING: [
                self.STATUS_READY,
                self.STATUS_CANCELLED,
            ],
            self.STATUS_READY: [
                self.STATUS_PAID,
                self.STATUS_COMPLETED,
                self.STATUS_CANCELLED,
            ],
            self.STATUS_PAID: [
                self.STATUS_COMPLETED,
            ],
        }

        if new_status not in allowed.get(self.status, []):
            raise ValidationError(
                f"Invalid transition {self.status} → {new_status}"
            )

        self.status = new_status
        timestamp = occurred_at or timezone.now()

        if new_status == self.STATUS_ACCEPTED:
            self.accepted_at = timestamp
        elif new_status == self.STATUS_PREPARING:
            self.preparing_at = timestamp
        elif new_status == self.STATUS_READY:
            self.ready_at = timestamp
        elif new_status == self.STATUS_CANCELLED:
            self.cancelled_at = timestamp
        elif new_status == self.STATUS_COMPLETED:
            self.completed_at = timestamp

        self.save()

        # -----------------------------------------
        # 🔥 Auto Close TableSession
        # -----------------------------------------
        if new_status in [self.STATUS_COMPLETED, self.STATUS_CANCELLED]:

            remaining_active_orders = self.session.orders.filter(
                status__in=[
                    self.STATUS_CREATED,
                    self.STATUS_ACCEPTED,
                    self.STATUS_PREPARING,
                    self.STATUS_READY,
                    self.STATUS_PAID,
                ]
            ).exists()

            # If NO active orders remain → close session
            if not remaining_active_orders:
                self.session.status = TableSession.STATUS_CLOSED
                self.session.closed_at = timezone.now()
                self.session.save(update_fields=["status", "closed_at"])

                transaction.on_commit(
                    lambda: publish_session_closed(self.session)
                )


# each item of the order is data for AI to predict the time
class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        related_name="items",
        on_delete=models.CASCADE,
    )

    dish_id = models.CharField(max_length=20, db_index=True)
    dish_name = models.CharField(max_length=255)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    image_url = models.URLField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    order_item_version = models.CharField(max_length=10, default="v1")

    class Meta:
        indexes = [
            models.Index(fields=["dish_id"]),
        ]

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * Decimal(self.quantity)
        super().save(*args, **kwargs)
        self.order.recalculate_totals()

    def __str__(self):
        return f"{self.quantity} × {self.dish_name}"
