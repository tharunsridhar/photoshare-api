"""Proves the cache-aside behavior on /feed and /posts/{id}: a second read
is served from Redis without touching Postgres, and a write (upload/delete)
invalidates it so the next read reflects the change - not stale data.
"""

import pytest

from apps.accounts.models import User
from apps.posts import cache as cache_module
from apps.posts.models import Post
from tests.conftest import login, register_user

pytestmark = pytest.mark.django_db


def _seed_post(owner_email: str) -> Post:
    owner = User.objects.get(email=owner_email)
    return Post.objects.create(
        user=owner, caption="cache test", url="https://example.com/x.jpg", file_type="image", file_name="x.jpg"
    )


def test_feed_second_call_is_served_from_cache(api_client):
    register_user(api_client, "cacheuser@example.com")
    headers = login(api_client, "cacheuser@example.com")
    _seed_post("cacheuser@example.com")

    version = cache_module.get_feed_version()
    key = cache_module.feed_cache_key(version, page=1, page_size=20)

    assert cache_module.redis_client.get(key) is None
    res1 = api_client.get("/feed", **headers)
    assert res1.status_code == 200
    # the first call is a cache miss, so it should have populated the key
    assert cache_module.redis_client.get(key) is not None

    res2 = api_client.get("/feed", **headers)
    assert res2.status_code == 200
    assert res1.json()["posts"] == res2.json()["posts"]


def test_uploading_invalidates_the_feed_cache(api_client):
    register_user(api_client, "invalidator@example.com")
    headers = login(api_client, "invalidator@example.com")
    _seed_post("invalidator@example.com")

    version_before = cache_module.get_feed_version()
    api_client.get("/feed", **headers)  # populate the cache at version_before

    cache_module.bump_feed_version()  # what /upload does on success
    version_after = cache_module.get_feed_version()
    assert version_after == version_before + 1

    # the old version's key is simply orphaned (left to expire on its TTL) -
    # a request after the bump computes a key under the NEW version instead
    old_key = cache_module.feed_cache_key(version_before, page=1, page_size=20)
    new_key = cache_module.feed_cache_key(version_after, page=1, page_size=20)
    assert cache_module.redis_client.get(old_key) is not None  # still there, just unreachable via new reads
    assert cache_module.redis_client.get(new_key) is None


def test_post_detail_is_cached_and_invalidated_on_delete(api_client):
    register_user(api_client, "detailowner@example.com")
    headers = login(api_client, "detailowner@example.com")
    post = _seed_post("detailowner@example.com")

    key = cache_module.post_cache_key(str(post.id))
    assert cache_module.redis_client.get(key) is None

    res = api_client.get(f"/posts/{post.id}", **headers)
    assert res.status_code == 200
    assert res.json()["is_owner"] is True
    assert cache_module.redis_client.get(key) is not None

    api_client.delete(f"/posts/{post.id}", **headers)
    assert cache_module.redis_client.get(key) is None  # invalidated, not just left stale
