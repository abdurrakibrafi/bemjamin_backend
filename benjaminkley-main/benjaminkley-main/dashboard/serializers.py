from rest_framework import serializers
from django.contrib.auth.models import User
from authentication.models import UserProfile
from scans.models import Scan
from contact_support.models import ContactMessage
from .models import AdminNotification, SiteContent
from authentication.serializers import PasswordValidator
from django.conf import settings 
from django.urls import reverse
from core.utils import get_full_media_url
from urllib.parse import urljoin

class DashboardUserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source='profile.role', read_only=True)
    status = serializers.CharField(source='profile.status')
    date_of_birth = serializers.DateField(source='profile.date_of_birth', read_only=True)
    number_of_scan = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ('id','first_name','last_name','email','profile_picture','role','date_of_birth','number_of_scan','status','date_joined')
    def get_profile_picture(self, obj):
        request = self.context.get('request')
        return get_full_media_url(request, obj.profile.profile_picture)
    def get_number_of_scan(self, obj):
        return obj.scans.count()
    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        status = profile_data.get('status')
        profile = instance.profile
        if status is not None:
            profile.status = status
            profile.save()
        return super().update(instance, validated_data)


class DashboardScanSerializer(serializers.ModelSerializer):
    scan_id = serializers.UUIDField(source='id', read_only=True)
    name = serializers.CharField(source='user.get_full_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    submission_date = serializers.DateTimeField(source='created_at', read_only=True)
    reconstructed_3d_head = serializers.SerializerMethodField()
    pdf_report_url = serializers.SerializerMethodField()
    scan_images = serializers.SerializerMethodField()
    head_width = serializers.CharField()
    head_height = serializers.CharField()
    head_length = serializers.CharField()
    ear_to_ear = serializers.CharField()
    eye_to_eye = serializers.CharField()
    head_circumference_A = serializers.CharField()
    forehead_to_back_B = serializers.CharField()
    cross_measurement_C = serializers.CharField()
    under_chin_D = serializers.CharField()
    eyebrow_to_earlobe_E = serializers.CharField()
    eye_corner_to_ear_F = serializers.CharField()
    ear_height_G = serializers.CharField()
    ear_width_H = serializers.CharField()
    cheek_guard_clearance_L = serializers.CharField()
    cheek_guard_height_M = serializers.CharField()
    cheek_guard_width_N = serializers.CharField()
    class Meta:
        model = Scan
        fields = (
            'scan_id',
            'name',
            'email',
            'submission_date',
            'status',
            'notes',
            'custom_field',
            'reconstructed_3d_head',
            'scan_images',
            'pdf_report_url',
            'head_width',
            'head_height',
            'head_length',
            'ear_to_ear',
            'eye_to_eye',
            'head_circumference_A',
            'forehead_to_back_B',
            'cross_measurement_C',
            'under_chin_D',
            'eyebrow_to_earlobe_E',
            'eye_corner_to_ear_F',
            'ear_height_G',
            'ear_width_H',
            'cheek_guard_clearance_L',
            'cheek_guard_height_M',
            'cheek_guard_width_N'
        )

    def get_pdf_report_url(self, obj):
        if obj.status == Scan.Status.COMPLETED:
            path = reverse('dashboard-scan-view-pdf', kwargs={'pk': obj.pk})
            return urljoin(str(settings.SERVER_BASE_URL), path)
        return None

    def get_reconstructed_3d_head(self, obj):
        request = self.context.get('request')
        return get_full_media_url(request, obj.processed_3d_model)

    def get_scan_images(self, obj):
        request = self.context.get('request')
        images = []
        
        front_url = get_full_media_url(request, obj.image_front)
        if front_url:
            images.append(front_url)
            
        for extra in obj.extra_images.all():
            url = get_full_media_url(request, extra.image)
            if url:
                images.append(url)
        
        return {
            "thumbnail": front_url,
            "all_images": images
        }

class DashboardContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = '__all__'

class PushNotificationSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()

class AdminNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminNotification
        fields = ('id', 'notification_type', 'title', 'message', 'is_read', 'created_at')

class SiteContentSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)
    class Meta:
        model = SiteContent
        fields = '__all__'

class AdminProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name')
    email = serializers.EmailField()
    contact_number = serializers.CharField(source='profile.contact_number')
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ('full_name', 'email', 'contact_number', 'profile_picture')
    def get_profile_picture(self, obj):
        request = self.context.get('request')
        return get_full_media_url(request, obj.profile.profile_picture)

class AdminUpdateProfileSerializer(serializers.ModelSerializer):
    profile_picture = serializers.ImageField(required=False, write_only=True)
    class Meta:
        model = UserProfile
        fields = ('contact_number', 'profile_picture')

class AdminChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    confirm_new_password = serializers.CharField(write_only=True, required=True)
    
    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is not correct.")
        return value
    
    def validate(self, data):
        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError("New passwords do not match.")
        return data