import django_filters
from django.utils import timezone
from .models import Scan

class ScanDateFilter(django_filters.FilterSet):
    month = django_filters.NumberFilter(field_name='created_at', lookup_expr='month')
    created_today = django_filters.BooleanFilter(method='filter_created_today')
    start_date = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')
    specific_date = django_filters.DateFilter(field_name='created_at__date')
    class Meta:
        model = Scan
        fields = ['month', 'created_today', 'start_date', 'end_date', 'specific_date']

    def filter_created_today(self, queryset, name, value):
        if value:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today)
        return queryset