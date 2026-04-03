from django.db import models
from django.utils import timezone
from utils.id_generator import generate_unique_id
from tickets.kafka.producer import publish_kitchen_event

class KitchenTicket(models.Model):
    
    public_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )
    restaurant_id = models.CharField(
        max_length=20,
        db_index=True,
    )
    order_id = models.CharField(max_length=20, db_index=True)
    user_id = models.CharField(max_length=20)

   
    STATUS_RECEIVED = "RECEIVED"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_PREPARING = "PREPARING"
    STATUS_READY = "READY"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = (
        (STATUS_RECEIVED, "Received"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_READY, "Ready"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RECEIVED,
        db_index=True,
    )

    # ⏱ Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    kitchenTicket_version = models.CharField(max_length=10,default="v1")
    # -------------------------
    # 🔧 Meta
    # -------------------------
    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["order_id"]),
        ]

    # -------------------------
    # 🔒 Business Logic
    # -------------------------
    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = generate_unique_id("KT")
        super().save(*args, **kwargs)


    def accept(self):
        if self.status != self.STATUS_RECEIVED:
            raise ValueError("Ticket cannot be accepted")

        self.status = self.STATUS_ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at", "updated_at"])
        publish_kitchen_event("ACCEPTED", self)


    def start_preparing(self):
        if self.status != self.STATUS_ACCEPTED:
            raise ValueError("Ticket must be accepted first")

        self.status = self.STATUS_PREPARING
        self.preparing_at = timezone.now()
        self.save(update_fields=["status", "preparing_at", "updated_at"])
        publish_kitchen_event("PREPARING", self)


    def mark_ready(self):
        if self.status != self.STATUS_PREPARING:
            raise ValueError("Ticket is not in preparing state")

        self.status = self.STATUS_READY
        self.ready_at = timezone.now()
        self.save(update_fields=["status", "ready_at", "updated_at"])
        publish_kitchen_event("READY", self)


    def cancel(self):
        if self.status == self.STATUS_CANCELLED:
            return  
        self.status = self.STATUS_CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancelled_at", "updated_at"])


    def __str__(self):
        return f"KitchenTicket({self.public_id}) → Order({self.order_id})"





class KitchenItem(models.Model):
    
    ticket = models.ForeignKey(
        KitchenTicket,
        related_name="items",
        on_delete=models.CASCADE,
    )
    restaurant_id = models.CharField(
        max_length=20,
        db_index=True,
    )
    dish_id = models.CharField(max_length=20, db_index=True)
    dish_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()

    STATUS_PENDING = "PENDING"
    STATUS_PREPARING = "PREPARING"
    STATUS_READY = "READY"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_READY, "Ready"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    prep_time_seconds = models.IntegerField(null=True, blank=True)
    estimated_prep_time_seconds = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    kitchenItem_version = models.CharField(max_length=10,default="v1")
    class Meta:
        indexes = [
            models.Index(fields=["dish_id"]),
            models.Index(fields=["status"]),
        ]

    # -------------------------
    # 🔒 Business Logic
    # -------------------------
    def save(self, *args, **kwargs):
        if not self.restaurant_id:
            self.restaurant_id = self.ticket.restaurant_id
        super().save(*args, **kwargs)


    def start_preparing(self):
        if self.status != self.STATUS_PENDING:
            raise ValueError("Item not ready to prepare")

        self.status = self.STATUS_PREPARING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_ready(self):
        if self.status != self.STATUS_PREPARING:
            raise ValueError("Item not in preparing state")

        self.status = self.STATUS_READY
        self.finished_at = timezone.now()
        self.prep_time_seconds = int(
            (self.finished_at - self.started_at).total_seconds()
        )
        self.save(
            update_fields=[
                "status",
                "finished_at",
                "prep_time_seconds",
            ]
        )

    def cancel(self):
        self.status = self.STATUS_CANCELLED
        self.save(update_fields=["status"])

    def __str__(self):
        return f"{self.dish_name} × {self.quantity} ({self.status})"