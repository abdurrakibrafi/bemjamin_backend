# scans/processing.py
import logging
from .models import Scan
from .processing.pipeline import run_full_scan_pipeline, PipelineError
from decimal import Decimal
from notifications.utils import create_and_send_notification
from dashboard.models import AdminNotification

logger = logging.getLogger(__name__)

def process_scan_and_save(scan_id: str):
    logger.info(f"Starting processing for scan {scan_id}")
    scan = Scan.objects.get(id=scan_id)
    try:
        AdminNotification.objects.create(
            notification_type=AdminNotification.NotificationType.NEW_SCAN,
            message=f"User {scan.user.get_full_name()} has submitted a new scan for processing: '{scan.name}'."
        )

        results = run_full_scan_pipeline(scan)
        measurements = results.get('measurements', {})
        
        scan.head_width = Decimal(measurements.get('head_width', 0))
        scan.head_length = Decimal(measurements.get('head_length', 0))
        scan.ear_to_ear = Decimal(measurements.get('ear_to_ear', 0))
        scan.eye_to_eye = Decimal(measurements.get('eye_to_eye', 0))
        scan.head_height = Decimal(measurements.get('head_height', 0))
        scan.head_circumference_A = Decimal(measurements.get('head_circumference_A', 0))
        scan.forehead_to_back_B = Decimal(measurements.get('forehead_to_back_B', 0))
        scan.cross_measurement_C = Decimal(measurements.get('cross_measurement_C', 0))
        scan.under_chin_D = Decimal(measurements.get('under_chin_D', 0))
        scan.eyebrow_to_earlobe_E = Decimal(measurements.get('eyebrow_to_earlobe_E', 0))
        scan.eye_corner_to_ear_F = Decimal(measurements.get('eye_corner_to_ear_F', 0))
        scan.ear_height_G = Decimal(measurements.get('ear_height_G', 0))
        scan.ear_width_H = Decimal(measurements.get('ear_width_H', 0))
        scan.cheek_guard_clearance_L = Decimal(measurements.get('cheek_guard_clearance_L', 0))
        scan.cheek_guard_height_M = Decimal(measurements.get('cheek_guard_height_M', 0))
        scan.cheek_guard_width_N = Decimal(measurements.get('cheek_guard_width_N', 0))
        
        scan.status = Scan.Status.COMPLETED
        logger.info(f"Completed processing for scan {scan_id}")

    except (PipelineError, Exception) as e:
        scan.status = Scan.Status.FAILED
        scan.failure_reason = str(e)
        logger.error(f"Failed processing for scan {scan_id}: {e}")

    finally:
        scan.save()
        
        if scan.status == Scan.Status.COMPLETED:
            create_and_send_notification(
                user=scan.user,
                title="Scan Completed",
                message=f"Your scan '{scan.name}' has been successfully processed."
            )
        elif scan.status == Scan.Status.FAILED:
            create_and_send_notification(
                user=scan.user,
                title="Scan Failed",
                message=f"There was an error processing your scan '{scan.name}'. Please try again or contact support."
            )