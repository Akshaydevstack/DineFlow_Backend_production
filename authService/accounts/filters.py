import django_filters
from .models import CustomUserModel


class EmployeeFilter(django_filters.FilterSet):
    created_at_after  = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="date__gte",
    )
    created_at_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="date__lte",
    )

    class Meta:
        model  = CustomUserModel
        fields = {
            "role":      ["exact"],
            "is_active": ["exact"],
        }