from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import RegexValidator
from phonenumber_field.modelfields import PhoneNumberField

import uuid

class Roles(models.TextChoices):
    ADMIN = 'ADMIN', 'Admin'
    DOCTOR = 'DOCTOR', 'Doctor'
    PROVIDER = 'PROVIDER', 'Provider'
    CLIENT = 'CLIENT', 'Client'
    STAFF = 'STAFF', 'Staff'
    CLINIC = 'CLINIC', 'Clinic'
    PRIVATE_USER = 'PRIVATE_USER', 'Private User'
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    role = models.CharField(max_length=50, choices=Roles.choices, default=Roles.CLIENT)
    clinic_name = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField()
    contact_number = PhoneNumberField(region=None, blank=True, null=True)
    class Status(models.TextChoices):
        UNVERIFIED = 'UNVERIFIED', 'Unverified'
        PENDING = 'PENDING', 'Pending'
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'

    status = models.CharField(max_length=50, choices=Status.choices, default=Status.UNVERIFIED)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    address = models.CharField(max_length=255)
    has_accepted_terms = models.BooleanField(default=False)
    login_count = models.PositiveIntegerField(default=0)

    def __repr__(self):
        return f"<User object: {self.user.first_name} {self.user.last_name}>"

class AuthToken(models.Model):
    TOKEN_TYPES = (
        ('signup', 'Signup Verification'),
        ('password_reset_otp', 'Password Reset OTP'),
        ('password_change_ticket', 'Password Change Ticket'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_tokens')
    token_type = models.CharField(max_length=30, choices=TOKEN_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=15)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

class PasswordHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    hashed_password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        histories = PasswordHistory.objects.filter(user=self.user).order_by('-created_at')
        if histories.count() > 10:
            histories.last().delete()