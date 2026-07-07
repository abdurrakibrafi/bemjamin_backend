from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .serializers import ContactMessageSerializer
from dashboard.models import AdminNotification
from notifications.utils import create_and_send_notification

class SubmitContactMessageView(generics.CreateAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        AdminNotification.objects.create(
            notification_type=AdminNotification.NotificationType.NEW_CONTACT,
            message=f"New contact message received from {request.data.get('name')} ({request.data.get('email')})."
        )
        
        create_and_send_notification(
            user=request.user,
            title="Support Message Received",
            message="We have received your message and will get back to you shortly."
        )
        
        response_data = {
            "message": "Your message has been successfully submitted. Our support team will review it shortly."
        }
        headers = self.get_success_headers(serializer.data)
    
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)