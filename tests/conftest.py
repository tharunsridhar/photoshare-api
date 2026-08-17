"""Shared fixtures. pytest-django's db access (via pytestmark =
pytest.mark.django_db in each test file) gives every test a transaction
that's rolled back afterward - same isolation goal as the FastAPI port's
SAVEPOINT-based db_session fixture, just via pytest-django's own mechanism.
"""

import pytest
from rest_framework.test import APIClient

from apps.posts.cache import redis_client


@pytest.fixture()
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _flush_cache():
    """Mirrors the FastAPI port's _fresh_redis_client fixture: a stale
    feed/post cache key from a previous test (same version, same page)
    could otherwise get served to this one."""
    redis_client.flushdb()
    yield


def register_user(client: APIClient, email: str, password: str = "testpass123") -> dict:
    res = client.post("/auth/register", {"email": email, "password": password}, format="json")
    res_json = res.json()
    assert res.status_code == 201, res_json
    return res_json


def login(client: APIClient, email: str, password: str = "testpass123") -> dict:
    """The login endpoint is OAuth2-password-form-shaped (field is
    "username" even though the value is an email) - matches the FastAPI
    port's login endpoint exactly. Returns request kwargs, not just a
    header value, since Django's test client takes auth as **kwargs."""
    res = client.post("/auth/jwt/login", {"username": email, "password": password})
    res_json = res.json()
    assert res.status_code == 200, res_json
    token = res_json["access_token"]
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
