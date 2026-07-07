from django.db import models
class AdminNotification(models.Model):
    class NotificationType(models.TextChoices):
        NEW_USER = 'NEW_USER', 'New User Signup'
        NEW_SCAN = 'NEW_SCAN', 'New Scan Submitted'
        NEW_CONTACT = 'NEW_CONTACT', 'New Contact Message'
        PUSH_SENT = 'PUSH_SENT', 'Push Notification Sent'
    
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices
    )
    
    title = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField() 
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return f"{self.get_notification_type_display()}: {self.message[:50]}"

class SiteContent(models.Model):
    slug = models.SlugField(unique=True, primary_key=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.title