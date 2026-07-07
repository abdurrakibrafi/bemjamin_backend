#!/bin/sh
set -e
. /opt/venv/bin/activate

COMMAND=$1

if [ "$COMMAND" = "migrate" ]; then
    echo "--- Running migrations and collectstatic ---"
    python manage.py migrate --no-input
    python manage.py collectstatic --no-input --clear

elif [ "$COMMAND" = "web" ]; then
    echo "--- Starting Gunicorn ---"
    exec gunicorn benjaminkley.wsgi --bind 0.0.0.0:8000 --workers 3 --timeout 120

elif [ "$COMMAND" = "celery-worker" ]; then
    echo "--- Starting Celery worker ---"
    exec celery -A benjaminkley worker -l info

elif [ "$COMMAND" = "celery-beat" ]; then
    echo "--- Starting Celery beat ---"
    exec celery -A benjaminkley beat -l info --pidfile /tmp/celerybeat.pid

else
    exec "$@"
fi