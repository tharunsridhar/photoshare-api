"""Celery application: broker (task queue) and result backend both live in
Redis, on a separate logical DB (index 1) from the cache (index 0) so a
`FLUSHDB` on one doesn't wipe the other."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "photoshare",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
