import logging
from fcm_django.models import FCMDevice
from .models import Notification
from firebase_admin import messaging

logger = logging.getLogger(__name__)

def create_and_send_notification(user, title, message):
    Notification.objects.create(
        user=user,
        title=title,
        message=message
    )

    try:
        devices = FCMDevice.objects.filter(user=user, active=True)
        if devices.exists():
            devices.send_message(
                messaging.Message(
                    notification=messaging.Notification(title=title, body=message)
                )
            )
            logger.info(
                "Sent push notification to %d device(s) for user %s.",
                devices.count(), user.username
            )
        else:
            logger.debug(
                "No active devices for user %s. Push notification skipped.",
                user.username
            )
    except Exception as e:
        logger.exception(
            "Failed to send push notification for user %s: %s", user.username, e
        )