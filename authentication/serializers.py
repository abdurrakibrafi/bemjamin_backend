import re
import hashlib
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from rest_framework import serializers
from .models import UserProfile, PasswordHistory, Roles
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.urls import reverse
from fcm_django.models import FCMDevice
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from core.utils import get_full_media_url

class RoleChoiceField(serializers.ChoiceField):
    def to_internal_value(self, data):
        for key, value in self._choices.items():
            if value == data:
                return key
        self.fail('invalid_choice', input=data)

class PasswordValidator:
    @staticmethod
    def validate_breached_password(password):
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            api_url = getattr(settings, 'PWNED_PASSWORDS_API_URL', 'https://api.pwnedpasswords.com/range/')
            response = requests.get(f"{api_url}{prefix}", timeout=3)
            return suffix in response.text
        except requests.RequestException:
            return False

    @staticmethod
    def validate_password_strength(password):
        if len(password) < 10:
            raise serializers.ValidationError("Password must be at least 10 characters long.")
        if not re.search(r"[A-Z]", password):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", password):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise serializers.ValidationError("Password must contain at least one special character.")

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    confirm_password = serializers.CharField(write_only=True, required=True)
    first_name = serializers.CharField(max_length=255, required=True)
    last_name = serializers.CharField(max_length=255, required=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    role = RoleChoiceField(choices=Roles.choices)
    clinic_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=True, input_formats=['%m-%d-%Y'])
    contact_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(max_length=255, required=True)
    terms_accepted = serializers.BooleanField(write_only=True)

    def validate(self, data):
        role = data.get('role')
        clinic_name = data.get('clinic_name')

        if role != Roles.PRIVATE_USER and not clinic_name:
            raise serializers.ValidationError({"clinic_name": "Clinic name is required for this role."})
            
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        if User.objects.filter(email__iexact=data['email']).exists():
            raise serializers.ValidationError({"email": "An account with this email already exists."})
        if not data.get('terms_accepted'):
            raise serializers.ValidationError({"terms_accepted": "You must agree to the terms and conditions to register."})
        data.pop('confirm_password', None)
        return data

    def create(self, validated_data):
        validated_data.pop('terms_accepted', None)
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name'),
            last_name=validated_data.get('last_name'),
            is_active=False
        )
        profile = user.profile
        profile.role = validated_data.get('role', profile.role)
        clinic_name = validated_data.get('clinic_name')
        if not clinic_name:
            clinic_name = "N/A"
        profile.clinic_name = clinic_name
        profile.date_of_birth = validated_data.get('date_of_birth', profile.date_of_birth)
        profile.contact_number = validated_data.get('contact_number', profile.contact_number)
        profile.address = validated_data.get('address', profile.address)
        profile.has_accepted_terms = True
        profile.profile_picture = validated_data.get('profile_picture', profile.profile_picture)
        profile.save()
        return user

class OTPVerificationSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, min_length=6)

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[PasswordValidator.validate_password_strength])
    new_password_confirmation = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct.")
        return value

    def validate_new_password(self, value):
        user = self.context['request'].user
        if PasswordValidator.validate_breached_password(value):
            raise serializers.ValidationError("This password has been found in a data breach. Please choose a different one.")
        if user.check_password(value):
            raise serializers.ValidationError("New password cannot be the same as the old password.")
        for history in PasswordHistory.objects.filter(user=user).order_by('-created_at')[:10]:
            if check_password(value, history.hashed_password):
                raise serializers.ValidationError("Cannot reuse a recent password.")
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirmation']:
            raise serializers.ValidationError({"new_password_confirmation": "New passwords do not match."})
        return data

class ProfileSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    email = serializers.EmailField(source='user.email', read_only=True)
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'email', 'profile_picture', 'role',
            'clinic_name', 'date_of_birth', 'contact_number', 'address', 'status'
        ]

    def get_profile_picture(self, obj):
        request = self.context.get('request')
        return get_full_media_url(request, obj.profile_picture)

class UpdateProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    profile_picture = serializers.ImageField(required=False)
    role = RoleChoiceField(choices=Roles.choices, required=False)
    clinic_name = serializers.CharField(required=False)
    date_of_birth = serializers.DateField(required=False)
    address = serializers.CharField(required=False)

    def update(self, instance, validated_data):
        profile = instance.profile
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        profile.profile_picture = validated_data.get('profile_picture', profile.profile_picture)
        profile.role = validated_data.get('role', profile.role)
        profile.clinic_name = validated_data.get('clinic_name', profile.clinic_name)
        profile.date_of_birth = validated_data.get('date_of_birth', profile.date_of_birth)
        profile.address = validated_data.get('address', profile.address)
        instance.save()
        profile.save()
        return instance

class ProfilePictureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['profile_picture']
    def update(self, instance, validated_data):
        instance.profile_picture = validated_data.get('profile_picture', instance.profile_picture)
        instance.save()
        return instance

class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.CharField()

class MyTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    fcmToken = serializers.CharField(required=False, write_only=True, allow_blank=True)
    device_type = serializers.ChoiceField(choices=[('ios', 'ios'), ('android', 'android'), ('web', 'web')], required=False, write_only=True)
    class Meta:
        fields = ['email', 'password', 'fcmToken', 'device_type']

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError('Email and password are required.')

        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('No account found with this email address.')

        if not user_obj.is_active:
            try:
                profile = user_obj.profile
                if profile.status == 'UNVERIFIED':
                    raise serializers.ValidationError('Your account is not active. Please verify your email first.')
                elif profile.status == 'PENDING':
                    raise serializers.ValidationError('Your account is awaiting admin approval.')
                elif profile.status == 'SUSPENDED':
                    raise serializers.ValidationError('Your account has been suspended by an administrator.')
                else:
                    raise serializers.ValidationError('This account is inactive.')
            except UserProfile.DoesNotExist:
                raise serializers.ValidationError('An error occurred with your profile. Please contact support.')

        user = authenticate(username=user_obj.username, password=password)

        if user is None:
            raise serializers.ValidationError('You have entered a wrong email or password.')

        try:
            profile = user.profile
            profile.login_count += 1
            profile.save(update_fields=['login_count'])
        except UserProfile.DoesNotExist:
            profile, created = UserProfile.objects.get_or_create(user=user)
            if created:
                profile.login_count = 1
                profile.save(update_fields=['login_count'])
        refresh = RefreshToken.for_user(user)

        fcmToken = attrs.get('fcmToken')
        device_type = attrs.get('device_type')
        if fcmToken and device_type:
            FCMDevice.objects.update_or_create(
                registration_id=fcmToken,
                defaults={
                    'user': user,
                    'type': device_type,
                    'active': True
                }
            )

        return {
            'custom_meta': {
                "message": "Successfully Logged in."
            },
            "user": {
                "id": user.pk,
                "email": user.email,
                "role": "ADMIN" if user.is_staff else user.profile.role,
                "has_accepted_terms": user.profile.has_accepted_terms,
                "login_count": user.profile.login_count
            },
            "token": str(refresh.access_token),
            "refresh_token": str(refresh)
        }

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

class PasswordResetVerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, min_length=6)

class SetNewPasswordSerializer(serializers.Serializer):
    password_change_ticket = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    new_password_confirmation = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        if data['new_password'] != data['new_password_confirmation']:
            raise serializers.ValidationError({"new_password_confirmation": "Passwords do not match."})
        if PasswordValidator.validate_breached_password(data['new_password']):
            raise serializers.ValidationError({
                "new_password": "This password is too common and has been seen before. Please choose a more unique password."
            })
        return data
class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Your password was incorrect. Please try again.")
        return value