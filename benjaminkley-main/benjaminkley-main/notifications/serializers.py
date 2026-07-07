from rest_framework import serializers
from .models import Notification
from fcm_django.models import FCMDevice

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'title', 'message', 'is_read', 'created_at')