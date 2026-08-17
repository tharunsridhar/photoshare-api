"""Background jobs. Run in a separate Celery worker process, off the
request path - so an upload response doesn't wait on anything beyond the
ImageKit upload itself. Unlike the FastAPI port (which needs a separate sync
SQLAlchemy engine for the worker, since its app engine is async-only),
Django's ORM is sync everywhere, so this just imports the same models
directly - no second engine to maintain."""

from django.conf import settings

from apps.posts.models import Post
from config.celery import app as celery_app


def _build_thumbnail_url(original_url: str) -> str:
    """ImageKit serves resized variants via a URL segment, not a separate
    upload - inserting tr:w-300,h-300,fo-auto right after the endpoint asks
    ImageKit's CDN to generate (and cache) a 300x300 smart-cropped version
    on first request. No new file, no extra storage to manage ourselves."""
    prefix = settings.IMAGEKIT_URL.rstrip("/")
    if original_url.startswith(prefix):
        rest = original_url[len(prefix) :].lstrip("/")
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
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        # the post was deleted before this task ran - nothing to do, and
        # definitely not a reason to retry
        return
    if post.thumbnail_url is not None:
        # already done - makes this task safe to enqueue twice (a retry
        # after a partial failure, a duplicate delivery from the broker)
        # without doing the work, or the DB write, a second time
        return
    post.thumbnail_url = _build_thumbnail_url(post.url)
    post.save(update_fields=["thumbnail_url"])
