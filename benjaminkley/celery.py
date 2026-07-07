import os
from celery import Celery
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benjaminkley.settings')

app = Celery('benjaminkley')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {
    'flush-expired-jwt-tokens-nightly': {
        'task': 'benjaminkley.tasks.flush_expired_tokens',
        'schedule': timedelta(hours=24),
        'options': {'expires': 3600},
    },
}
app.conf.beat_max_loop_interval = 60
