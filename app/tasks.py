"""Background jobs. Run in a separate Celery worker process, off the request
path - so an upload response doesn't wait on anything beyond the ImageKit
upload itself.

Celery workers are plain sync processes, so this uses its own sync
SQLAlchemy engine/session - separate from the app's async engine in
app/db.py, but pointed at the same database.
"""

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import settings
from app.db import Post

_sync_engine = create_engine(settings.database_url, pool_pre_ping=True)
_SyncSession = sessionmaker(bind=_sync_engine)


def _build_thumbnail_url(original_url: str) -> str:
    """ImageKit serves resized variants via a URL segment, not a separate
    upload - inserting tr:w-300,h-300,fo-auto right after the endpoint asks
    ImageKit's CDN to generate (and cache) a 300x300 smart-cropped version
    on first request. No new file, no extra storage to manage ourselves."""
    prefix = settings.imagekit_url.rstrip("/")
    if original_url.startswith(prefix):
        rest = original_url[len(prefix):].lstrip("/")
        return f"{prefix}/tr:w-300,h-300,fo-auto/{rest}"
    return original_url


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def generate_thumbnail_task(self, post_id: str) -> None:
    with _SyncSession() as session:
        post = session.get(Post, uuid.UUID(post_id))
        if post is None:
            # the post was deleted before this task ran - nothing to do,
            # and definitely not a reason to retry
            return
        if post.thumbnail_url is not None:
            # already done - makes this task safe to enqueue twice (a retry
            # after a partial failure, a duplicate delivery from the broker)
            # without doing the work, or the DB write, a second time
            return
        post.thumbnail_url = _build_thumbnail_url(post.url)
        session.commit()
