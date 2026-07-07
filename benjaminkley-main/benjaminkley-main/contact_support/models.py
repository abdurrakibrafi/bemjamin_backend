from django.db import models
from django.contrib.auth.models import User

class ContactMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="The user who sent the message.")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    message = models.TextField()
    is_replied = models.BooleanField(default=False, help_text="Has an admin replied to this message?")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Message from {self.name} ({self.email})"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"