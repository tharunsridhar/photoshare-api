"""Ownership-based authorization: only a post's owner can delete it, and the
feed correctly flags which posts belong to the requesting user.

Posts are seeded directly via the ORM rather than through /upload, which
calls the real ImageKit API - not something to depend on in a test suite."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Post, User
from tests.conftest import login, register_user

pytestmark = pytest.mark.asyncio


async def _seed_post(db_session: AsyncSession, owner_email: str) -> Post:
    owner = (await db_session.execute(select(User).where(User.email == owner_email))).scalar_one()
    post = Post(
        user_id=owner.id,
        caption="A test post",
        url="https://example.com/fake.jpg",
        file_type="image",
        file_name="fake.jpg",
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)
    return post


async def test_owner_can_delete_their_own_post(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "owner@example.com")
    headers = await login(client, "owner@example.com")
    post = await _seed_post(db_session, "owner@example.com")

    res = await client.delete(f"/posts/{post.id}", headers=headers)
    assert res.status_code == 200

    remaining = (await db_session.execute(select(Post).where(Post.id == post.id))).scalar_one_or_none()
    assert remaining is None


async def test_non_owner_cannot_delete_someone_elses_post(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "owner2@example.com")
    await register_user(client, "intruder@example.com")
    headers = await login(client, "intruder@example.com")
    post = await _seed_post(db_session, "owner2@example.com")

    res = await client.delete(f"/posts/{post.id}", headers=headers)
    assert res.status_code == 403

    still_there = (await db_session.execute(select(Post).where(Post.id == post.id))).scalar_one_or_none()
    assert still_there is not None


async def test_deleting_a_nonexistent_post_returns_404(client: AsyncClient):
    await register_user(client, "nobody-owns-this@example.com")
    headers = await login(client, "nobody-owns-this@example.com")
    res = await client.delete(f"/posts/{uuid.uuid4()}", headers=headers)
    assert res.status_code == 404


async def test_deleting_with_an_invalid_id_returns_400(client: AsyncClient):
    await register_user(client, "badid@example.com")
    headers = await login(client, "badid@example.com")
    res = await client.delete("/posts/not-a-uuid", headers=headers)
    assert res.status_code == 400


async def test_deleting_a_post_requires_authentication(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "owner3@example.com")
    post = await _seed_post(db_session, "owner3@example.com")
    res = await client.delete(f"/posts/{post.id}")
    assert res.status_code == 401


async def test_feed_flags_ownership_correctly_per_viewer(client: AsyncClient, db_session: AsyncSession):
    await register_user(client, "author@example.com")
    await register_user(client, "viewer@example.com")
    post = await _seed_post(db_session, "author@example.com")

    author_headers = await login(client, "author@example.com")
    author_feed = (await client.get("/feed", headers=author_headers)).json()["posts"]
    author_entry = next(p for p in author_feed if p["id"] == str(post.id))
    assert author_entry["is_owner"] is True

    viewer_headers = await login(client, "viewer@example.com")
    viewer_feed = (await client.get("/feed", headers=viewer_headers)).json()["posts"]
    viewer_entry = next(p for p in viewer_feed if p["id"] == str(post.id))
    assert viewer_entry["is_owner"] is False
    assert viewer_entry["email"] == "author@example.com"
