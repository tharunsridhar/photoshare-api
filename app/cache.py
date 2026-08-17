"""Cache-aside helpers for the feed and post-detail read paths.

Cache-aside: on a read, check Redis first; on a miss, read the DB and
populate the cache; on a write, don't try to update the cache in place -
just invalidate it, and let the next read repopulate it. Trying to keep a
cache in sync with every write is the hard, bug-prone part of caching;
invalidating and letting the next read rebuild it is simpler and correct as
long as invalidation itself is reliable.

Feed invalidation specifically uses a version counter rather than deleting
keys directly: every feed page is cached under a key that embeds the current
version (feed:v3:p1:s20). A write bumps the version once - every existing
page's key instantly stops being addressed by future reads (they compute a
new key with the new version) and just expires on its own TTL. That avoids
having to enumerate and delete every cached page (there could be many, and
Redis's KEYS/SCAN pattern-matching approach doesn't belong on a request
path). Post-detail cache is a single well-known key per post, so it's
invalidated directly - no versioning needed for that one.
"""

import json
from typing import Any

import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def get_json(key: str) -> Any | None:
    raw = await redis_client.get(key)
    return json.loads(raw) if raw is not None else None


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    await redis_client.set(key, json.dumps(value), ex=ttl_seconds)


async def get_feed_version() -> int:
    version = await redis_client.get("feed:version")
    return int(version) if version is not None else 0


async def bump_feed_version() -> None:
    await redis_client.incr("feed:version")


def feed_cache_key(version: int, page: int, page_size: int) -> str:
    return f"feed:v{version}:p{page}:s{page_size}"


def post_cache_key(post_id: str) -> str:
    return f"post:{post_id}"


async def invalidate_post_cache(post_id: str) -> None:
    await redis_client.delete(post_cache_key(post_id))
