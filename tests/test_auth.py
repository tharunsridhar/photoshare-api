"""Auth lifecycle: registration, login, email verification, and password
reset. Verification/reset tokens normally go out by email - this app has no
mail service wired up (apps.accounts.services just prints the token), so
tests capture the token directly from request_verify()/forgot_password()'s
return value and drive the rest through the real HTTP endpoints."""

import pytest

from apps.accounts.models import User
from apps.accounts.services import forgot_password, request_verify
from tests.conftest import login, register_user

pytestmark = pytest.mark.django_db


def test_register_creates_a_user(api_client):
    body = register_user(api_client, "newuser@example.com")
    assert body["email"] == "newuser@example.com"
    assert body["is_active"] is True
    assert body["is_verified"] is False


def test_register_rejects_duplicate_email(api_client):
    register_user(api_client, "dupe@example.com")
    res = api_client.post("/auth/register", {"email": "dupe@example.com", "password": "testpass123"}, format="json")
    assert res.status_code == 400


def test_login_succeeds_with_correct_credentials(api_client):
    register_user(api_client, "logintest@example.com", "correctpass123")
    res = api_client.post("/auth/jwt/login", {"username": "logintest@example.com", "password": "correctpass123"})
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_rejects_wrong_password(api_client):
    register_user(api_client, "wrongpass@example.com", "correctpass123")
    res = api_client.post("/auth/jwt/login", {"username": "wrongpass@example.com", "password": "wrongpass"})
    assert res.status_code == 400


def test_login_rejects_unknown_email(api_client):
    res = api_client.post("/auth/jwt/login", {"username": "nobody@example.com", "password": "whatever123"})
    assert res.status_code == 400


def test_authenticated_request_requires_a_valid_token(api_client):
    res = api_client.get("/users/me")
    assert res.status_code == 401

    res = api_client.get("/users/me", HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert res.status_code == 401


def test_authenticated_request_succeeds_with_a_valid_token(api_client):
    register_user(api_client, "me@example.com")
    headers = login(api_client, "me@example.com")
    res = api_client.get("/users/me", **headers)
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"


def test_email_verification_flow(api_client):
    register_user(api_client, "verifyme@example.com")
    user = User.objects.get(email="verifyme@example.com")
    assert user.is_verified is False

    token = request_verify(user)

    res = api_client.post("/auth/verify", {"token": token}, format="json")
    assert res.status_code == 200
    assert res.json()["is_verified"] is True

    user.refresh_from_db()
    assert user.is_verified is True


def test_verification_rejects_an_unknown_token(api_client):
    res = api_client.post("/auth/verify", {"token": "not-a-real-token"}, format="json")
    assert res.status_code == 400


def test_password_reset_flow(api_client):
    register_user(api_client, "forgetful@example.com", "oldpassword123")
    user = User.objects.get(email="forgetful@example.com")
    token = forgot_password(user)

    res = api_client.post("/auth/reset-password", {"token": token, "password": "newpassword456"}, format="json")
    assert res.status_code == 200

    # old password no longer works, new one does
    old = api_client.post("/auth/jwt/login", {"username": "forgetful@example.com", "password": "oldpassword123"})
    assert old.status_code == 400
    new = api_client.post("/auth/jwt/login", {"username": "forgetful@example.com", "password": "newpassword456"})
    assert new.status_code == 200


def test_reset_password_rejects_an_unknown_token(api_client):
    res = api_client.post(
        "/auth/reset-password", {"token": "not-a-real-token", "password": "whatever123"}, format="json"
    )
    assert res.status_code == 400
