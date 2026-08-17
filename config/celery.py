"""Celery application, bound to Django settings. Broker (task queue) and
result backend both live in Redis, on a separate logical DB (index 1) from
the cache (index 0) - see CELERY_BROKER_URL/CELERY_RESULT_BACKEND in
config/settings/base.py."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("photoshare")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
