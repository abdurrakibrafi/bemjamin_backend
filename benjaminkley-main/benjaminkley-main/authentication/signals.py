from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(
            user=instance,
            role='Admin',  
            clinic_name='N/A',
            date_of_birth='1900-01-01', 
            contact_number=None, 
            address='N/A'
        )