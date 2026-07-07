import logging
from celery import shared_task
from django.core import management

logger = logging.getLogger(__name__)


@shared_task(name='benjaminkley.tasks.flush_expired_tokens')
def flush_expired_tokens():
    try:
        logger.info("Starting flush_expired_tokens task...")
        management.call_command('flushexpiredtokens')
        logger.info("flush_expired_tokens completed successfully.")
    except Exception as e:
        logger.exception("flush_expired_tokens task failed: %s", e)
