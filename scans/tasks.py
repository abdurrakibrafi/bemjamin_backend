import os
from celery import shared_task
import logging
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
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


@shared_task
def send_quota_exceeded_admin_email(scan_id: str):
    """
    Sends an alert email to administrator(s) when KeenTools quota is reached
    and a scan is placed on hold in PENDING_APPROVAL status.
    """
    logger.info(f"Preparing KeenTools quota alert email for scan {scan_id}")
    try:
        scan = Scan.objects.select_related('user').get(id=scan_id)
        from .models import KeenToolsQuota
        quota = KeenToolsQuota.get_singleton()

        recipient_list = []
        admin_env = os.getenv('ADMIN_NOTIFICATION_EMAIL') or getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', None)
        if admin_env:
            recipient_list.extend([e.strip() for e in admin_env.split(',') if e.strip()])

        User = get_user_model()
        staff_emails = list(
            User.objects.filter(is_active=True, is_staff=True)
            .exclude(email='')
            .values_list('email', flat=True)
        )
        recipient_list.extend(staff_emails)

        if not recipient_list:
            from authentication.models import Roles
            role_admin_emails = list(
                User.objects.filter(is_active=True, profile__role=Roles.ADMIN)
                .exclude(email='')
                .values_list('email', flat=True)
            )
            recipient_list.extend(role_admin_emails)

        # Deduplicate recipient list while preserving order
        recipient_list = list(dict.fromkeys(recipient_list))

        if not recipient_list:
            logger.warning(
                "No admin email addresses found to send KeenTools quota alert for scan %s.", scan_id
            )
            return False

        user_name = scan.user.get_full_name() or scan.user.username or scan.user.email
        subject = f"[Action Required] KeenTools Quota Limit Reached ({quota.used_scans}/{quota.max_scans})"
        message = (
            f"Hello Admin,\n\n"
            f"The KeenTools maximum scan limit ({quota.max_scans}) has been reached on the platform.\n\n"
            f"A new scan has been placed on hold and requires admin review or a quota reset:\n\n"
            f"• Scan Name: {scan.name}\n"
            f"• Scan ID: {scan.id}\n"
            f"• Submitted By: {user_name} ({scan.user.email})\n"
            f"• Status: PENDING_APPROVAL\n"
            f"• Current Quota: {quota.used_scans}/{quota.max_scans}\n\n"
            f"Actions Available:\n"
            f"1. Review and approve the scan from the Admin Dashboard.\n"
            f"2. Reset or increase the KeenTools quota from the dashboard or via POST /api/dashboard/keentools-quota/reset/.\n\n"
            f"Regards,\n"
            f"Benjaminkley System"
        )

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(
            "KeenTools quota alert email successfully sent to %s for scan %s",
            recipient_list, scan_id
        )
        return True
    except Exception as exc:
        logger.exception(
            "Failed to send KeenTools quota alert email for scan %s: %s",
            scan_id, exc
        )
        return False