from rest_framework import serializers
from .models import Scan, ScanImage
from django.conf import settings
from django.urls import reverse
from core.utils import get_full_media_url
from urllib.parse import urljoin
import os

class ScanCreateSerializer(serializers.ModelSerializer):
    image_front = serializers.ImageField(required=True)
    
    extra_images = serializers.ListField(
        child=serializers.ImageField(max_length=1000000, allow_empty_file=False, use_url=False),
        write_only=True,
        required=True
    )

    class Meta:
        model = Scan
        fields = ('name', 'notes', 'custom_field', 'image_front', 'extra_images', 'calibration_type', 'calibration_value')

    def _validate_image_file(self, image):
        MAX_SIZE = 50 * 1024 * 1024
        if image.size > MAX_SIZE:
            raise serializers.ValidationError(f"Image {image.name} is too large. Max size is 50MB.")
        
        valid_types = ['image/jpeg', 'image/png', 'image/jpg']
        if image.content_type not in valid_types:
            ext = os.path.splitext(image.name)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png']:
                raise serializers.ValidationError(f"Image {image.name} has invalid format. Only JPG/PNG allowed.")

    def validate_image_front(self, value):
        self._validate_image_file(value)
        return value

    def validate(self, attrs):
        front = attrs.get('image_front')
        extras = attrs.get('extra_images', [])
        
        total_images = 1 + len(extras)
        if total_images < 5:
            raise serializers.ValidationError(f"You uploaded {total_images} images. Minimum 5 required (Recommended 8-10 for full 360° coverage).")
        
        for img in extras:
            self._validate_image_file(img)

        return attrs

    def create(self, validated_data):
        extra_images_data = validated_data.pop('extra_images')
        
        scan = Scan.objects.create(**validated_data)
        
        scan_images = [ScanImage(scan=scan, image=img) for img in extra_images_data]
        ScanImage.objects.bulk_create(scan_images)
        
        return scan

class ScanDetailSerializer(serializers.ModelSerializer):
    scan_id = serializers.UUIDField(source='id', read_only=True)
    Name = serializers.CharField(source='name', default="N/A")
    Date_of_Scan = serializers.DateTimeField(source='created_at', format="%B %d, %Y", read_only=True)
    status = serializers.CharField()
    
    scan_images = serializers.SerializerMethodField()
    reconstructed_3d_head = serializers.SerializerMethodField()
    pdf_report_url = serializers.SerializerMethodField()
    
    Head_Width = serializers.CharField(source='head_width')
    Head_Length = serializers.CharField(source='head_length')
    Ear_to_Ear = serializers.CharField(source='ear_to_ear')
    Eye_to_Eye = serializers.CharField(source='eye_to_eye')
    Head_Circumference_A = serializers.CharField(source='head_circumference_A')
    Forehead_to_Back_B = serializers.CharField(source='forehead_to_back_B')
    Cross_Measurement_C = serializers.CharField(source='cross_measurement_C')
    Under_Chin_D = serializers.CharField(source='under_chin_D')
    Eyebrow_to_Earlobe_E = serializers.CharField(source='eyebrow_to_earlobe_E')
    Eye_Corner_to_Ear_F = serializers.CharField(source='eye_corner_to_ear_F')
    Ear_Height_G = serializers.CharField(source='ear_height_G')
    Ear_Width_H = serializers.CharField(source='ear_width_H')
    Notes = serializers.CharField(source='notes')
    Custom_Fit = serializers.CharField(source='custom_field')
    calibration_type = serializers.CharField()
    calibration_value = serializers.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        model = Scan
        fields = (
            'scan_id', 'Name', 'Date_of_Scan', 'status',
            'scan_images', 'reconstructed_3d_head', 'pdf_report_url',
            'calibration_type', 'calibration_value',
            'Head_Width', 'Head_Length', 'Ear_to_Ear', 'Eye_to_Eye',
            'Head_Circumference_A', 'Forehead_to_Back_B', 'Cross_Measurement_C', 'Under_Chin_D',
            'Eyebrow_to_Earlobe_E', 'Eye_Corner_to_Ear_F', 'Ear_Height_G', 'Ear_Width_H',
            'Notes', 'Custom_Fit'
        )


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
        
        return {"thumbnail": front_url, "all_images": images}

    def get_reconstructed_3d_head(self, obj):
        request = self.context.get('request')
        return get_full_media_url(request, obj.processed_3d_model)

    def get_pdf_report_url(self, obj):
        if obj.status == Scan.Status.COMPLETED:
            path = reverse('scan-view-pdf', kwargs={'pk': obj.pk})
            return urljoin(str(settings.SERVER_BASE_URL), path)
        return None