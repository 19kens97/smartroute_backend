import re

import django_filters
from django.db.models import Q

from apps.vehicles.models import normalize_plate_number
from .models import Alert
from .serializers import ALERT_SEVERITIES, ALERT_TYPE_LABELS


class AlertFilter(django_filters.FilterSet):
    alert_type = django_filters.MultipleChoiceFilter(choices=Alert.TYPE_CHOICES)
    source = django_filters.MultipleChoiceFilter(choices=Alert.SOURCE_CHOICES)
    severity = django_filters.MultipleChoiceFilter(
        choices=(('INFO', 'INFO'), ('WARNING', 'WARNING'), ('CRITICAL', 'CRITICAL')),
        method='filter_severity',
    )
    plate_number = django_filters.CharFilter(method='filter_plate_number')
    search = django_filters.CharFilter(method='filter_search')
    created_after = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Alert
        fields = ('alert_type', 'created_by', 'source')

    def filter_plate_number(self, queryset, name, value):
        normalized = normalize_plate_number(value)
        return queryset.filter(plate_number__iexact=normalized) if normalized else queryset.none()

    def filter_search(self, queryset, name, value):
        term = str(value or '').strip()
        if not term:
            return queryset

        matching_types = [
            alert_type
            for alert_type, label in ALERT_TYPE_LABELS.items()
            if term.upper() in alert_type.upper() or term.casefold() in label.casefold()
        ]
        normalized_plate = normalize_plate_number(term)
        query = Q(description__icontains=term) | Q(alert_type__icontains=term)
        if normalized_plate:
            compact_plate = normalized_plate.replace('-', '')
            query |= Q(plate_number__icontains=normalized_plate) | Q(plate_number__icontains=compact_plate)
            if compact_plate:
                compact_pattern = r'[^A-Z0-9]*'.join(re.escape(char) for char in compact_plate)
                query |= Q(plate_number__iregex=compact_pattern)
        if matching_types:
            query |= Q(alert_type__in=matching_types)
        return queryset.filter(query)

    def filter_severity(self, queryset, name, values):
        selected = set(values)
        alert_types = [
            alert_type for alert_type, severity in ALERT_SEVERITIES.items() if severity in selected
        ]
        return queryset.filter(alert_type__in=alert_types) if alert_types else queryset.none()
