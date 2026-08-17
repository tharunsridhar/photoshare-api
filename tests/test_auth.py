"""Auth lifecycle: registration, login, email verification, and password
reset. Verification/reset tokens normally go out by email - this app has no
mail service wired up (on_after_request_verify just prints), so tests
capture the token the same way an email template would (see
user_manager_factory in conftest.py) and drive the rest through the real
HTTP endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import User
from tests.conftest import login, register_user

pytestmark = pytest.mark.asyncio


async def test_register_creates_a_user(client: AsyncClient):
    body = await register_user(client, "newuser@example.com")
    assert body["email"] == "newuser@example.com"
    assert body["is_active"] is True
    assert body["is_verified"] is False


async def test_register_rejects_duplicate_email(client: AsyncClient):
    await register_user(client, "dupe@example.com")
    res = await client.post("/auth/register", json={"email": "dupe@example.com", "password": "testpass123"})
    assert res.status_code == 400


async def test_login_succeeds_with_correct_credentials(client: AsyncClient):
    await register_user(client, "logintest@example.com", "correctpass123")
    res = await client.post("/auth/jwt/login", data={"username": "logintest@example.com", "password": "correctpass123"})
    assert res.status_code == 200
    assert res.json()["access_token"]


async def test_login_rejects_wrong_password(client: AsyncClient):
    await register_user(client, "wrongpass@example.com", "correctpass123")
    res = await client.post("/auth/jwt/login", data={"username": "wrongpass@example.com", "password": "wrongpass"})
    assert res.status_code == 400


async def test_login_rejects_unknown_email(client: AsyncClient):
    res = await client.post("/auth/jwt/login", data={"username": "nobody@example.com", "password": "whatever123"})
    assert res.status_code == 400


async def test_authenticated_request_requires_a_valid_token(client: AsyncClient):
    res = await client.get("/users/me")
    assert res.status_code == 401

    res = await client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


async def test_authenticated_request_succeeds_with_a_valid_token(client: AsyncClient):
    await register_user(client, "me@example.com")
    headers = await login(client, "me@example.com")
    res = await client.get("/users/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"


async def test_email_verification_flow(client: AsyncClient, db_session: AsyncSession, user_manager_factory):
    await register_user(client, "verifyme@example.com")
    manager, capture = user_manager_factory()

    user = (await db_session.execute(select(User).where(User.email == "verifyme@example.com"))).scalar_one()
    assert user.is_verified is False

    await manager.request_verify(user)
    assert capture.token is not None

    res = await client.post("/auth/verify", json={"token": capture.token})
    assert res.status_code == 200
    assert res.json()["is_verified"] is True

    await db_session.refresh(user)
    assert user.is_verified is True


async def test_verification_rejects_an_unknown_token(client: AsyncClient):
    res = await client.post("/auth/verify", json={"token": "not-a-real-token"})
    assert res.status_code == 400


async def test_password_reset_flow(client: AsyncClient, db_session: AsyncSession, user_manager_factory):
    await register_user(client, "forgetful@example.com", "oldpassword123")
    manager, capture = user_manager_factory()

    user = (await db_session.execute(select(User).where(User.email == "forgetful@example.com"))).scalar_one()
    await manager.forgot_password(user)
    assert capture.token is not None

    res = await client.post("/auth/reset-password", json={"token": capture.token, "password": "newpassword456"})
    assert res.status_code == 200

    # old password no longer works, new one does
    old = await client.post("/auth/jwt/login", data={"username": "forgetful@example.com", "password": "oldpassword123"})
    assert old.status_code == 400
    new = await client.post("/auth/jwt/login", data={"username": "forgetful@example.com", "password": "newpassword456"})
    assert new.status_code == 200


async def test_reset_password_rejects_an_unknown_token(client: AsyncClient):
    res = await client.post("/auth/reset-password", json={"token": "not-a-real-token", "password": "whatever123"})
    assert res.status_code == 400
