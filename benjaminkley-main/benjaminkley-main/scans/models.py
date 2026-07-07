from django.db import models
from django.contrib.auth.models import User
import uuid

class Scan(models.Model):
    class Status(models.TextChoices):
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scans')

    name = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)
    custom_field = models.CharField(max_length=255, blank=True, null=True)
    image_front = models.ImageField(upload_to='scans/inputs/') 

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    failure_reason = models.TextField(null=True, blank=True)
    processed_3d_model = models.FileField(upload_to='scans/outputs/', null=True, blank=True)
    
    eye_to_eye = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ear_to_ear = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    head_width = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    head_height = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    head_length = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    head_circumference_A = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    forehead_to_back_B = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cross_measurement_C = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    under_chin_D = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    eyebrow_to_earlobe_E = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    eye_corner_to_ear_F = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ear_height_G = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ear_width_H = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cheek_guard_clearance_L = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cheek_guard_height_M = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cheek_guard_width_N = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Scan '{self.name}'"

class ScanImage(models.Model):
    scan = models.ForeignKey(Scan, related_name='extra_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='scans/inputs/')
    created_at = models.DateTimeField(auto_now_add=True)