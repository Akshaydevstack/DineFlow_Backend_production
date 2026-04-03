import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import DishReview

class DishReviewFilter(django_filters.FilterSet):
    created_at_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_at_to   = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = DishReview
        fields = ["dish", "show_review", "rating", "created_at_from", "created_at_to"]
