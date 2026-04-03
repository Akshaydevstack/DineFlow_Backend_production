import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from restaurant.models import Restaurant 
from .managers import CustomUserManager
from django.utils.text import slugify
import hashlib
# ==========================================
# 🔹 Utility Functions
# ==========================================

def generate_public_id(role, restaurant_id=None):
   
    prefix = role[:3].upper() 
    rand = uuid.uuid4().hex[:6].upper()

    if restaurant_id:
        return f"{prefix}-{restaurant_id[:4].upper()}-{rand}"
    
    return f"{prefix}-GLO-{rand}"


# ==========================================
# 🔹 Custom User Model
# ==========================================

class CustomUserModel(AbstractUser):
    
    username = models.CharField(max_length=255, unique=True)
    
    last_name = None  

    email = models.EmailField(null=True, blank=True)

    ROLE_CHOICES = (
        ("super-admin", "Super-Admin"),
        ("restaurant-admin", "Restaurant-Admin"),
        ("waiter", "Waiter"),
        ("kitchen-staff", "Kitchen-Staff"),
        ("customer", "Customer"),
    )

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="customer"
    )

    
    mobile_number = models.CharField(
        max_length=15,
        db_index=True 
    )

   
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE, 
        related_name="users",
        null=True, 
        blank=True
    )

    public_id = models.CharField(
        max_length=100,
        unique=True,
        editable=False,
    )

   
    current_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    current_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    
    is_superadmin = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    auth_version = models.CharField(max_length=50,default="v1")
   
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["mobile_number", "email"] 

    objects = CustomUserManager()
    
    class Meta:

        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["restaurant"]),
            models.Index(fields=["public_id"]),
            models.Index(fields=["mobile_number", "restaurant"]), 
        ]

        constraints = [
            models.UniqueConstraint(
                fields=['restaurant', 'mobile_number'],
                name='unique_mobile_per_restaurant'
            ),
            
            models.UniqueConstraint(
                fields=['mobile_number'],
                condition=models.Q(restaurant__isnull=True),
                name='unique_mobile_for_superadmin'
            )
        ]


    def save(self, *args, **kwargs):

        if self.role == "super-admin":
            self.restaurant = None
            self.is_superadmin = True
            self.username = self.email

        else:
            if not self.restaurant:
                raise ValueError(f"{self.role} must belong to a restaurant.")

            if self.is_staff and self.role == "restaurant-admin":
                self.username = self.email

                        
            elif self.is_staff:
              
                restaurant_base = (
                    self.restaurant.slug
                    if self.restaurant.slug
                    else slugify(self.restaurant.name)
                )
                restaurant_code = restaurant_base.replace("-", "")[:2]

                role_code = slugify(self.role).replace("-", "")[:2]

                base = self.public_id or f"{self.role}-{self.email}-{self.mobile_number}"
                unique_code = hashlib.sha1(base.encode()).hexdigest()[:6]

                self.username = f"{restaurant_code}{role_code}{unique_code}"

            else:
                rest_id_str = str(self.restaurant.public_id)
                self.username = f"{rest_id_str}_{self.mobile_number}"

        if not self.public_id:
            rest_id = str(self.restaurant.public_id) if self.restaurant else "SYS"
            self.public_id = generate_public_id(self.role, rest_id)

        super().save(*args, **kwargs)

    def __str__(self):
        if self.restaurant:
            return f"{self.mobile_number} @ {self.restaurant.name}"
        return f"{self.mobile_number} (Superadmin)"


# ==========================================
# 🔹 User Address Model
# ==========================================

class UserAddress(models.Model):
    user = models.ForeignKey(
        CustomUserModel,
        on_delete=models.CASCADE,
        related_name="addresses"
    )
    auth_version = models.CharField(max_length=50,default="v1")
    label = models.CharField(max_length=50)  
    address_line = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_default"]),
        ]

    def save(self, *args, **kwargs):
        
        if self.is_default:
            UserAddress.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)