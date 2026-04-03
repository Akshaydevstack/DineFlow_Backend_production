
import django_filters
from .models import KitchenTicket

class KitchenTicketFilter(django_filters.FilterSet):
    """
    Supports:
      ?created_at_after=2026-02-25   → tickets created on or after this date
      ?created_at_before=2026-03-27  → tickets created on or before this date
      ?status=PREPARING
    """
    created_at_after  = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="date__gte",
    )
    created_at_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="date__lte",
    )

    class Meta:
        model  = KitchenTicket
        fields = {
            "status":        ["exact"],
            "restaurant_id": ["exact"],
        }
