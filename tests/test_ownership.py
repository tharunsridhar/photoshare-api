"""Ownership-based authorization: only a post's owner can delete it, and the
feed correctly flags which posts belong to the requesting user.

Posts are seeded directly via the ORM rather than through /upload, which
calls the real ImageKit API - not something to depend on in a test suite."""

import uuid

import pytest

from apps.accounts.models import User
from apps.posts.models import Post
from tests.conftest import login, register_user

pytestmark = pytest.mark.django_db


def _seed_post(owner_email: str) -> Post:
    owner = User.objects.get(email=owner_email)
    return Post.objects.create(
        user=owner, caption="A test post", url="https://example.com/fake.jpg", file_type="image", file_name="fake.jpg"
    )


def test_owner_can_delete_their_own_post(api_client):
    register_user(api_client, "owner@example.com")
    headers = login(api_client, "owner@example.com")
    post = _seed_post("owner@example.com")

    res = api_client.delete(f"/posts/{post.id}", **headers)
    assert res.status_code == 200
    assert not Post.objects.filter(id=post.id).exists()


def test_non_owner_cannot_delete_someone_elses_post(api_client):
    register_user(api_client, "owner2@example.com")
    register_user(api_client, "intruder@example.com")
    headers = login(api_client, "intruder@example.com")
    post = _seed_post("owner2@example.com")

    res = api_client.delete(f"/posts/{post.id}", **headers)
    assert res.status_code == 403
    assert Post.objects.filter(id=post.id).exists()


def test_deleting_a_nonexistent_post_returns_404(api_client):
    register_user(api_client, "nobody-owns-this@example.com")
    headers = login(api_client, "nobody-owns-this@example.com")
    res = api_client.delete(f"/posts/{uuid.uuid4()}", **headers)
    assert res.status_code == 404


def test_deleting_with_an_invalid_id_returns_400(api_client):
    register_user(api_client, "badid@example.com")
    headers = login(api_client, "badid@example.com")
    res = api_client.delete("/posts/not-a-uuid", **headers)
    assert res.status_code == 400


def test_deleting_a_post_requires_authentication(api_client):
    register_user(api_client, "owner3@example.com")
    post = _seed_post("owner3@example.com")
    res = api_client.delete(f"/posts/{post.id}")
    assert res.status_code == 401


def test_feed_flags_ownership_correctly_per_viewer(api_client):
    register_user(api_client, "author@example.com")
    register_user(api_client, "viewer@example.com")
    post = _seed_post("author@example.com")

    author_headers = login(api_client, "author@example.com")
    author_feed = api_client.get("/feed", **author_headers).json()["posts"]
    author_entry = next(p for p in author_feed if p["id"] == str(post.id))
    assert author_entry["is_owner"] is True

    viewer_headers = login(api_client, "viewer@example.com")
    viewer_feed = api_client.get("/feed", **viewer_headers).json()["posts"]
    viewer_entry = next(p for p in viewer_feed if p["id"] == str(post.id))
    assert viewer_entry["is_owner"] is False
    assert viewer_entry["email"] == "author@example.com"
