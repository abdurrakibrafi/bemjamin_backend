import os
import io
import trimesh
import logging
from django.core.management.base import BaseCommand
from scans.models import Scan
from scans.mesh_measurements import perform_all_measurements

logger = logging.getLogger(__name__)


def load_mesh_from_scan(scan):
    """
    Load 3D mesh from scan.processed_3d_model safely, supporting both GLB and OBJ.
    """
    if not scan.processed_3d_model:
        return None

    loaded = None
    # 1. Try directly from filesystem path if accessible
    try:
        if hasattr(scan.processed_3d_model, 'path') and os.path.exists(scan.processed_3d_model.path):
            file_path = scan.processed_3d_model.path
            ext = os.path.splitext(file_path)[1].lower().lstrip('.')
            loaded = trimesh.load(file_path, file_type=ext if ext else None, force='mesh')
    except Exception as e:
        logger.debug(f"Direct file read failed, falling back to stream: {e}")

    # 2. Fallback: stream through BytesIO (e.g. S3 or storage backend)
    if loaded is None:
        try:
            content = scan.processed_3d_model.read()
            loaded = trimesh.load(io.BytesIO(content), file_type='glb', force='mesh')
        except Exception as e:
            logger.error(f"Could not load 3D model for scan {scan.id}: {e}")
            return None

    # Handle trimesh Scene container
    if isinstance(loaded, trimesh.Scene):
        meshes = [m for m in loaded.geometry.values() if isinstance(m, trimesh.Trimesh)]
        if not meshes:
            return None
        return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]

    return loaded


class Command(BaseCommand):
    help = "Recalculates biometric measurements on existing scans using the updated surface-distance pipeline."

    def add_arguments(self, parser):
        parser.add_argument('--scan-id', type=str, help='Specific Scan UUID to recalculate')
        parser.add_argument('--limit', type=int, default=5, help='Limit number of recent scans (default 5)')
        parser.add_argument('--all', action='store_true', help='Recalculate all completed scans')
        parser.add_argument('--cal-val', type=float, help='Override or provide calibration value in cm (e.g. --cal-val 60)')
        parser.add_argument('--save', action='store_true', help='Save newly computed measurements to database (default is dry-run)')

    def handle(self, *args, **options):
        scan_id = options.get('scan_id')
        recalc_all = options.get('all')
        limit = options.get('limit')
        save_to_db = options.get('save')

        if scan_id:
            scans = Scan.objects.filter(id=scan_id)
        elif recalc_all:
            scans = Scan.objects.filter(status=Scan.Status.COMPLETED, processed_3d_model__isnull=False).order_by('-created_at')
        else:
            scans = Scan.objects.filter(status=Scan.Status.COMPLETED, processed_3d_model__isnull=False).order_by('-created_at')[:limit]

        count = scans.count() if hasattr(scans, 'count') else len(scans)
        if count == 0:
            self.stdout.write(self.style.WARNING("No matching completed scans found with 3D models."))
            return

        mode_msg = "SAVING TO DATABASE" if save_to_db else "DRY RUN (preview only, no DB changes)"
        self.stdout.write(self.style.SUCCESS(f"\nFound {count} scan(s). Mode: {mode_msg}\n"))

        fields_to_compare = [
            ('head_circumference_A', 'A: Head Circumference'),
            ('forehead_to_back_B',   'B: Forehead to Back Arc'),
            ('cross_measurement_C',  'C: Cross Arc (Ear-to-Ear over vertex)'),
            ('under_chin_D',         'D: Under Chin Arc'),
            ('eyebrow_to_earlobe_E', 'E: Eyebrow to Earlobe (Surface)'),
            ('eye_corner_to_ear_F',  'F: Eye Corner to Ear Root (Surface)'),
            ('ear_height_G',         'G: Ear Height (Surface)'),
            ('ear_width_H',          'H: Ear Width (Surface)'),
            ('cheek_guard_clearance_L', 'L: Cheek Guard Clearance'),
            ('cheek_guard_height_M',    'M: Cheek Guard Height'),
            ('cheek_guard_width_N',     'N: Cheek Guard Width'),
            ('head_width',           'Head Width (Biparietal)'),
            ('head_height',          'Head Height'),
            ('head_length',          'Head Length'),
            ('ear_to_ear',           'Ear to Ear'),
            ('eye_to_eye',           'Eye to Eye'),
        ]

        override_cal = options.get('cal_val')

        for scan in scans:
            cal_val = override_cal if override_cal is not None else (float(scan.calibration_value) if scan.calibration_value else None)
            cal_type = 'USER_CIRCUMFERENCE' if override_cal is not None else scan.calibration_type

            self.stdout.write(self.style.MIGRATE_HEADING(f"═" * 70))
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"Scan: '{scan.name}' (ID: {scan.id})\n"
                f"User: {scan.user.username if scan.user else 'N/A'} | Created: {scan.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"Calibration: {cal_type} = {cal_val} cm {'(OVERRIDDEN via --cal-val)' if override_cal is not None else ''}"
            ))
            self.stdout.write(self.style.MIGRATE_HEADING(f"─" * 70))

            mesh = load_mesh_from_scan(scan)
            if mesh is None:
                self.stdout.write(self.style.ERROR(f"  ❌ Could not load 3D mesh from {scan.processed_3d_model}"))
                continue

            try:
                new_measurements = perform_all_measurements(
                    mesh,
                    calibration_type=cal_type,
                    calibration_value=cal_val
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Error computing measurements: {e}"))
                continue

            # Print comparison table
            header = f"  {'Measurement':<40} | {'Old Value':>10} | {'New Value':>10} | {'Diff':>8}"
            self.stdout.write(header)
            self.stdout.write("  " + "-" * 74)

            for field_name, label in fields_to_compare:
                old_val = getattr(scan, field_name)
                new_val = new_measurements.get(field_name)

                old_str = f"{float(old_val):.2f} cm" if old_val is not None else "N/A"
                new_str = f"{float(new_val):.2f} cm" if new_val is not None else "N/A"

                if old_val is not None and new_val is not None:
                    diff = float(new_val) - float(old_val)
                    diff_str = f"{diff:+.2f}"
                else:
                    diff_str = "-"

                self.stdout.write(f"  {label:<40} | {old_str:>10} | {new_str:>10} | {diff_str:>8}")

            if save_to_db:
                fields_to_update = list(new_measurements.keys())
                for key, val in new_measurements.items():
                    if hasattr(scan, key):
                        setattr(scan, key, val)
                if override_cal is not None:
                    scan.calibration_value = override_cal
                    scan.calibration_type = 'USER_CIRCUMFERENCE'
                    fields_to_update.extend(['calibration_value', 'calibration_type'])
                scan.save(update_fields=fields_to_update)
                self.stdout.write(self.style.SUCCESS(f"\n  ✅ Successfully updated Scan {scan.id} in database!"))
            else:
                self.stdout.write(self.style.NOTICE(f"\n  ℹ️ Dry-run mode: Pass --save to persist these new values to database."))

        self.stdout.write(self.style.MIGRATE_HEADING(f"═" * 70 + "\n"))
