from celery import shared_task
import logging
from django.db import transaction
from .processing.pipeline import run_full_scan_pipeline, PipelineError
from decimal import Decimal
from notifications.utils import create_and_send_notification
from dashboard.models import AdminNotification
from scans.models import Scan

logger = logging.getLogger(__name__)

@shared_task
def process_scan_and_save(scan_id: str):
    logger.info(f"Starting professional reconstruction for scan {scan_id}")
    
    try:
        scan = Scan.objects.get(id=scan_id)
        
        AdminNotification.objects.create(
            notification_type=AdminNotification.NotificationType.NEW_SCAN,
            message=f"User {scan.user.get_full_name()} submitted new scan: '{scan.name}'."
        )
        
        results = run_full_scan_pipeline(scan_id)
        
        scan.refresh_from_db()
        
        measurements = results.get('measurements', {})
        for key, value in measurements.items():
            if hasattr(scan, key) and value is not None:
                setattr(scan, key, Decimal(f"{value:.2f}"))
        
        scan.status = Scan.Status.COMPLETED
        scan.save() 
        
        logger.info(f"Completed processing for scan {scan_id}")
        
        create_and_send_notification(
            user=scan.user, 
            title="Scan Completed", 
            message=f"Your scan '{scan.name}' has been successfully processed."
        )

    except (PipelineError, Exception) as e:
        logger.exception(f"Failed processing for scan {scan_id}: {e}")

        try:
            scan = Scan.objects.get(id=scan_id)
            scan.status = Scan.Status.FAILED
            scan.failure_reason = str(e)
            scan.save()

            create_and_send_notification(
                user=scan.user,
                title="Scan Failed",
                message=f"There was an error processing your scan '{scan.name}'."
            )
        except Exception as fallback_exc:
            logger.exception(
                "Fallback failure handler also failed for scan %s: %s",
                scan_id, fallback_exc
            )