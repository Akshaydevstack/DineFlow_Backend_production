from django_filters import rest_framework as filters
from .models import Restaurant


class RestaurantFilter(filters.FilterSet):

    created_date = filters.DateFilter(field_name="created_at", lookup_expr="date")
    created_date_gte = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_date_lte = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Restaurant
        fields = [
            "is_active",
        ]