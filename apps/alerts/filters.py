import django_filters

from apps.vehicles.models import normalize_plate_number
from .models import Alert


class AlertFilter(django_filters.FilterSet):
    plate_number = django_filters.CharFilter(method="filter_plate_number")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Alert
        fields = ("alert_type", "created_by", "source")

    def filter_plate_number(self, queryset, name, value):
        normalized = normalize_plate_number(value)
        return queryset.filter(plate_number__iexact=normalized) if normalized else queryset.none()