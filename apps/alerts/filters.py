import re

import django_filters
from django.db.models import Q

from apps.vehicles.models import normalize_plate_number

from .models import Alert


class AlertFilter(django_filters.FilterSet):
    category = django_filters.MultipleChoiceFilter(
        choices=Alert.Category.choices
    )
    alert_type = django_filters.MultipleChoiceFilter(
        choices=Alert.AlertType.choices
    )
    specification = django_filters.MultipleChoiceFilter(
        choices=Alert._meta.get_field("specification").choices
    )
    source = django_filters.MultipleChoiceFilter(
        choices=Alert.Source.choices
    )
    severity = django_filters.MultipleChoiceFilter(
        choices=Alert.Severity.choices
    )
    status = django_filters.MultipleChoiceFilter(
        choices=Alert.Status.choices
    )
    plate_number = django_filters.CharFilter(
        method="filter_plate_number"
    )
    search = django_filters.CharFilter(
        method="filter_search"
    )
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )
    expires_before = django_filters.IsoDateTimeFilter(
        field_name="expires_at",
        lookup_expr="lte",
    )

    class Meta:
        model = Alert
        fields = (
            "category",
            "alert_type",
            "specification",
            "created_by",
            "source",
            "severity",
            "status",
        )

    def filter_plate_number(self, queryset, name, value):
        normalized = normalize_plate_number(value)

        return (
            queryset.filter(
                plate_number__iexact=normalized
            )
            if normalized
            else queryset.none()
        )

    def filter_search(self, queryset, name, value):
        term = str(value or "").strip()
        if not term:
            return queryset

        matching_types = [
            code
            for code, label in Alert.AlertType.choices
            if (
                term.upper() in code.upper()
                or term.casefold() in label.casefold()
            )
        ]
        normalized_plate = normalize_plate_number(term)

        query = (
            Q(description__icontains=term)
            | Q(alert_type__icontains=term)
            | Q(specification__icontains=term)
            | Q(subject_nif__icontains=term)
            | Q(resolution_note__icontains=term)
        )

        if normalized_plate:
            pattern = r"[^A-Z0-9]*".join(
                re.escape(character)
                for character in normalized_plate
            )
            query |= (
                Q(
                    plate_number__icontains=
                    normalized_plate
                )
                | Q(
                    plate_number__iregex=pattern
                )
            )

        if matching_types:
            query |= Q(
                alert_type__in=matching_types
            )

        return queryset.filter(query)
