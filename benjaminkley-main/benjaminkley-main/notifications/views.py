from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from fcm_django.models import FCMDevice
from .models import Notification
from .serializers import NotificationSerializer
from dashboard.pagination import CustomDashboardPagination

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = CustomDashboardPagination
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'], url_path='mark-all-as-read')
    def mark_all_as_read(self, request):
        self.get_queryset().update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)