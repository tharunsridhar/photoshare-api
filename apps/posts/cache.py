"""Cache-aside helpers for the feed and post-detail read paths - a direct
sync port of the FastAPI port's app/cache.py (same key scheme, same
feed-version-counter trick for invalidating every cached page in one write
instead of enumerating keys). Sync here because Django views are sync by
default and there's no async/await plumbing to thread through, unlike the
FastAPI side.

Feed invalidation uses a version counter: every feed page is cached under a
key that embeds the current version (feed:v3:p1:s20). A write bumps the
version once - every existing page's key instantly stops being addressed by
future reads and just expires on its own TTL. Post-detail cache is a single
well-known key per post, invalidated directly.
"""

import json
from typing import Any

import redis
from django.conf import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_json(key: str) -> Any | None:
    raw = redis_client.get(key)
    return json.loads(raw) if raw is not None else None


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    redis_client.set(key, json.dumps(value), ex=ttl_seconds)


def get_feed_version() -> int:
    version = redis_client.get("feed:version")
    return int(version) if version is not None else 0


def bump_feed_version() -> None:
    redis_client.incr("feed:version")


def feed_cache_key(version: int, page: int, page_size: int) -> str:
    return f"feed:v{version}:p{page}:s{page_size}"


def post_cache_key(post_id: str) -> str:
    return f"post:{post_id}"


def invalidate_post_cache(post_id: str) -> None:
    redis_client.delete(post_cache_key(post_id))
