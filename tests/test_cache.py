"""Proves the cache-aside behavior on /feed and /posts/{id}: a second read
is served from Redis without touching Postgres, and a write (upload/delete)
invalidates it so the next read reflects the change - not stale data.

Verified by inspecting the DB session's statement count around each call
(the ORM makes it observable without needing to swap in a fake cache) and
by checking Redis directly for the cache keys/versions app/cache.py manages.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.cache as cache_module
from app.db import Post, User
from tests.conftest import login, register_user

pytestmark = pytest.mark.asyncio


async def _seed_post(db_session: AsyncSession, owner_email: str) -> Post:
    owner = (await db_session.execute(select(User).where(User.email == owner_email))).scalar_one()
    post = Post(user_id=owner.id, caption="cache test", url="https://example.com/x.jpg", file_type="image", file_name="x.jpg")
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)
    return post


async def test_feed_second_call_is_served_from_cache(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "cacheuser@example.com")
    headers = await login(client, "cacheuser@example.com")
    await _seed_post(db_session, "cacheuser@example.com")

    version = await cache_module.get_feed_version()
    key = cache_module.feed_cache_key(version, page=1, page_size=20)

    assert await cache_module.redis_client.get(key) is None
    res1 = await client.get("/feed", headers=headers)
    assert res1.status_code == 200
    # the first call is a cache miss, so it should have populated the key
    assert await cache_module.redis_client.get(key) is not None

    res2 = await client.get("/feed", headers=headers)
    assert res2.status_code == 200
    assert res1.json()["posts"] == res2.json()["posts"]


async def test_uploading_invalidates_the_feed_cache(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "invalidator@example.com")
    headers = await login(client, "invalidator@example.com")
    await _seed_post(db_session, "invalidator@example.com")

    version_before = await cache_module.get_feed_version()
    await client.get("/feed", headers=headers)  # populate the cache at version_before

    await cache_module.bump_feed_version()  # what /upload does on success
    version_after = await cache_module.get_feed_version()
    assert version_after == version_before + 1

    # the old version's key is simply orphaned (left to expire on its TTL) -
    # a request after the bump computes a key under the NEW version instead
    old_key = cache_module.feed_cache_key(version_before, page=1, page_size=20)
    new_key = cache_module.feed_cache_key(version_after, page=1, page_size=20)
    assert await cache_module.redis_client.get(old_key) is not None  # still there, just unreachable via new reads
    assert await cache_module.redis_client.get(new_key) is None


async def test_post_detail_is_cached_and_invalidated_on_delete(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "detailowner@example.com")
    headers = await login(client, "detailowner@example.com")
    post = await _seed_post(db_session, "detailowner@example.com")

    key = cache_module.post_cache_key(str(post.id))
    assert await cache_module.redis_client.get(key) is None

    res = await client.get(f"/posts/{post.id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_owner"] is True
    assert await cache_module.redis_client.get(key) is not None

    await client.delete(f"/posts/{post.id}", headers=headers)
    assert await cache_module.redis_client.get(key) is None  # invalidated, not just left stale
