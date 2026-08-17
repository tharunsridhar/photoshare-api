"""Unlike the rest of the suite, this exercises /upload directly - by
mocking the ImageKit client rather than skipping it. Neither this port nor
the FastAPI one hits the real ImageKit API in tests, but mocking (instead of
just seeding Post rows via the ORM, as the other test files do) is enough to
actually cover the view's own logic: required-field validation, the 502 path
when ImageKit reports a non-200 status, and the error-response path when the
upload call itself raises."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.posts.models import Post
from apps.posts.tasks import generate_thumbnail_task
from tests.conftest import login, register_user

pytestmark = pytest.mark.django_db


def _fake_upload_result(status_code=200):
    return SimpleNamespace(
        url="https://ik.imagekit.io/test/photo_abc123.jpg",
        name="photo_abc123.jpg",
        response_metadata=SimpleNamespace(http_status_code=status_code),
    )


def test_upload_requires_a_file(api_client):
    register_user(api_client, "nofile@example.com")
    headers = login(api_client, "nofile@example.com")
    res = api_client.post("/upload", {"caption": "hi"}, format="multipart", **headers)
    assert res.status_code == 400


def test_upload_requires_a_caption(api_client, tmp_path):
    register_user(api_client, "nocaption@example.com")
    headers = login(api_client, "nocaption@example.com")
    fake_file = tmp_path / "photo.jpg"
    fake_file.write_bytes(b"not-really-a-jpeg")
    with fake_file.open("rb") as f:
        res = api_client.post("/upload", {"file": f}, format="multipart", **headers)
    assert res.status_code == 400


def test_upload_creates_a_post_and_dispatches_a_thumbnail_task(api_client, tmp_path):
    register_user(api_client, "uploader@example.com")
    headers = login(api_client, "uploader@example.com")
    fake_file = tmp_path / "photo.jpg"
    fake_file.write_bytes(b"not-really-a-jpeg")

    with (
        patch("apps.posts.views.imagekit.upload_file", return_value=_fake_upload_result()) as mock_upload,
        patch.object(generate_thumbnail_task, "delay") as mock_delay,
    ):
        with fake_file.open("rb") as f:
            res = api_client.post("/upload", {"file": f, "caption": "a real post"}, format="multipart", **headers)

    assert res.status_code == 201
    body = res.json()
    assert body["caption"] == "a real post"
    assert body["file_type"] == "image"
    assert body["url"] == "https://ik.imagekit.io/test/photo_abc123.jpg"
    mock_upload.assert_called_once()
    mock_delay.assert_called_once_with(body["id"])

    post = Post.objects.get(id=body["id"])
    assert post.user.email == "uploader@example.com"


def test_upload_returns_502_when_imagekit_reports_failure(api_client, tmp_path):
    register_user(api_client, "badupload@example.com")
    headers = login(api_client, "badupload@example.com")
    fake_file = tmp_path / "photo.jpg"
    fake_file.write_bytes(b"not-really-a-jpeg")

    with patch("apps.posts.views.imagekit.upload_file", return_value=_fake_upload_result(status_code=500)):
        with fake_file.open("rb") as f:
            res = api_client.post("/upload", {"file": f, "caption": "will fail"}, format="multipart", **headers)

    assert res.status_code == 502
    assert not Post.objects.filter(caption="will fail").exists()


def test_upload_returns_500_when_imagekit_call_raises(api_client, tmp_path):
    register_user(api_client, "network-error@example.com")
    headers = login(api_client, "network-error@example.com")
    fake_file = tmp_path / "photo.jpg"
    fake_file.write_bytes(b"not-really-a-jpeg")

    with patch("apps.posts.views.imagekit.upload_file", side_effect=ConnectionError("network down")):
        with fake_file.open("rb") as f:
            res = api_client.post("/upload", {"file": f, "caption": "will error"}, format="multipart", **headers)

    assert res.status_code == 500
    assert not Post.objects.filter(caption="will error").exists()


def test_upload_requires_authentication(api_client, tmp_path):
    fake_file = tmp_path / "photo.jpg"
    fake_file.write_bytes(b"not-really-a-jpeg")
    with fake_file.open("rb") as f:
        res = api_client.post("/upload", {"file": f, "caption": "no auth"}, format="multipart")
    assert res.status_code == 401
