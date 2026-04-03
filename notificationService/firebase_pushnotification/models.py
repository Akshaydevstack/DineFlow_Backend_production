# firebase_pushnotification/models.py
from django.db import models
from django.utils.timezone import now
import uuid


class DeviceToken(models.Model):
    user_id = models.CharField(max_length=50, db_index=True)
    role = models.CharField(max_length=20)
    restaurant_id = models.CharField(max_length=20, db_index=True)

    fcm_token = models.TextField(unique=True)
    device_type = models.CharField(
        max_length=20,
        choices=(("web", "Web"), ("android", "Android"), ("ios", "iOS")),
        default="web"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} ({self.device_type})"
    



class Notification(models.Model):

    user_id = models.CharField(max_length=100, db_index=True)

    title = models.CharField(max_length=255)
    body = models.TextField()

    topic = models.CharField(max_length=100, db_index=True)

    reference_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
    )

    is_read = models.BooleanField(default=False)

    is_broadcast = models.BooleanField(default=False)

    is_show = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=now)

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "topic"]),
        ]

    def save(self, *args, **kwargs):

        if not self.is_broadcast and not self.reference_id:
            self.reference_id = f"broadcast_{uuid.uuid4().hex[:12]}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Notification({self.user_id}, {self.topic})"