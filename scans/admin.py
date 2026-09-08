from django.contrib import admin
from .models import Scan, ScanImage
from django.db import models

class ScanImageInline(admin.TabularInline):
    model = ScanImage
    extra = 0
    readonly_fields = ('image', 'created_at')

@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin): 
    list_display = (
        'name',
        'user',
        'status',
        'created_at',
        'updated_at'
    )
    
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'user__username', 'id__iexact')
    
    inlines = [ScanImageInline]

    fieldsets = (
        ('Scan Details', {
            'fields': ('id', 'name', 'user', 'status', 'failure_reason')
        }),
        ('User Inputs', {
            'fields': ('notes', 'custom_field', 'image_front')
        }),
        ('Final Measurements (cm)', {
            'fields': (
                'eye_to_eye', 'ear_to_ear', 'head_width', 'head_height',
                'head_circumference_A', 'forehead_to_back_B', 'cross_measurement_C', 'under_chin_D',
                'eyebrow_to_earlobe_E', 'eye_corner_to_ear_F', 'ear_height_G', 'ear_width_H',
                'cheek_guard_clearance_L', 'cheek_guard_height_M', 'cheek_guard_width_N'
            )
        }),
        ('Output Files', {
            'fields': ('processed_3d_model',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    readonly_fields = ('id', 'user', 'created_at', 'updated_at', 'processed_3d_model', 'failure_reason') + \
                      tuple(f.name for f in Scan._meta.get_fields() if isinstance(f, models.DecimalField))

    actions = ['recalculate_measurements']

    def has_add_permission(self, request):
        return False

    @admin.action(description="Recalculate measurements with updated surface pipeline")
    def recalculate_measurements(self, request, queryset):
        from scans.management.commands.recalculate_measurements import load_mesh_from_scan
        from scans.mesh_measurements import perform_all_measurements
        from django.contrib import messages

        success_count = 0
        error_count = 0

        for scan in queryset:
            if not scan.processed_3d_model:
                continue
            mesh = load_mesh_from_scan(scan)
            if mesh is None:
                error_count += 1
                continue
            try:
                cal_val = float(scan.calibration_value) if scan.calibration_value else None
                measurements = perform_all_measurements(
                    mesh,
                    calibration_type=scan.calibration_type,
                    calibration_value=cal_val
                )
                for key, val in measurements.items():
                    if hasattr(scan, key):
                        setattr(scan, key, val)
                scan.save(update_fields=list(measurements.keys()))
                success_count += 1
            except Exception as e:
                error_count += 1

        if success_count > 0:
            self.message_user(
                request,
                f"Successfully recalculated measurements for {success_count} scan(s) using new surface pipeline.",
                messages.SUCCESS
            )
        if error_count > 0:
            self.message_user(
                request,
                f"Failed to recalculate {error_count} scan(s). Check logs for details.",
                messages.WARNING
            )